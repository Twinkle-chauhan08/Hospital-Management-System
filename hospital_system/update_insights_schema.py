import mysql.connector
from config import DevelopmentConfig as Config


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, table_name, index_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND index_name = %s
        LIMIT 1
        """,
        (table_name, index_name),
    )
    return cursor.fetchone() is not None


def update_schema_for_health_insights():
    """
    Adds missing tables/columns/indexes used by the app's Health Insights + booking logic
    without dropping existing data.
    """
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
        )
        cursor = conn.cursor()
        print("Connected to database...")

        # --- appointments extra fields ---
        appointment_columns = [
            ("treatment", "TEXT NULL"),
            ("bp", "VARCHAR(50) NULL"),
            ("weight", "VARCHAR(50) NULL"),
            ("prescription", "TEXT NULL"),
            ("next_visit_date", "DATE NULL"),
            ("slot_active", "TINYINT NULL DEFAULT 1"),
        ]
        for col_name, col_def in appointment_columns:
            if not _column_exists(cursor, "appointments", col_name):
                print(f"Adding appointments.{col_name}...")
                cursor.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_def}")
            else:
                print(f"appointments.{col_name} already exists.")

        # Slot lock normalization (mirrors app logic to avoid duplicate-slot conflicts)
        if _column_exists(cursor, "appointments", "slot_active"):
            print("Normalizing appointments.slot_active and time precision...")

            # Normalize second-level times to minute precision.
            cursor.execute(
                """
                UPDATE appointments
                SET appointment_time = MAKETIME(HOUR(appointment_time), MINUTE(appointment_time), 0)
                WHERE appointment_time IS NOT NULL
                  AND SECOND(appointment_time) <> 0
                """
            )

            # Backfill slot_active from status.
            cursor.execute(
                """
                UPDATE appointments
                SET slot_active = CASE
                    WHEN status IN ('Pending', 'Confirmed') THEN 1
                    ELSE NULL
                END
                WHERE slot_active IS NULL OR slot_active NOT IN (1)
                """
            )

            # Cancel old duplicates: keep latest appointment active, cancel older duplicates.
            cursor.execute(
                """
                UPDATE appointments a
                JOIN (
                    SELECT doctor_id,
                           appointment_date,
                           CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0')) AS slot_hhmm,
                           MAX(appointment_id) AS keep_id
                    FROM appointments
                    WHERE slot_active = 1
                    GROUP BY doctor_id, appointment_date,
                             CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0'))
                    HAVING COUNT(*) > 1
                ) d
                  ON d.doctor_id = a.doctor_id
                 AND d.appointment_date = a.appointment_date
                 AND d.slot_hhmm = CONCAT(LPAD(HOUR(a.appointment_time), 2, '0'), ':', LPAD(MINUTE(a.appointment_time), 2, '0'))
                SET a.status = CASE
                                   WHEN a.appointment_id = d.keep_id THEN a.status
                                   ELSE 'Cancelled'
                               END,
                    a.slot_active = CASE
                                       WHEN a.appointment_id = d.keep_id THEN 1
                                       ELSE NULL
                                   END
                WHERE a.appointment_id <> d.keep_id
                """
            )

        # Unique active slot index (allows multiple NULL slot_active rows)
        if not _index_exists(cursor, "appointments", "uniq_active_doctor_slot"):
            print("Creating unique index uniq_active_doctor_slot on appointments...")
            cursor.execute(
                """
                CREATE UNIQUE INDEX uniq_active_doctor_slot
                ON appointments (doctor_id, appointment_date, appointment_time, slot_active)
                """
            )
        else:
            print("Index uniq_active_doctor_slot already exists.")

        # --- profile photo columns ---
        if not _column_exists(cursor, "doctors", "photo_path"):
            print("Adding doctors.photo_path...")
            cursor.execute("ALTER TABLE doctors ADD COLUMN photo_path VARCHAR(255) NULL")
        else:
            print("doctors.photo_path already exists.")

        if not _column_exists(cursor, "receptionist", "photo_path"):
            print("Adding receptionist.photo_path...")
            cursor.execute("ALTER TABLE receptionist ADD COLUMN photo_path VARCHAR(255) NULL")
        else:
            print("receptionist.photo_path already exists.")

        # --- admins profile table (optional) ---
        print("Ensuring admins table exists...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                admin_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL DEFAULT 'Admin',
                email VARCHAR(120),
                phone VARCHAR(15),
                photo_path VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )

        # Seed an admin profile for the default admin account if present (safe to re-run)
        cursor.execute(
            """
            INSERT INTO admins (user_id, name, email, phone)
            SELECT u.user_id, 'Admin', NULL, NULL
            FROM users u
            WHERE u.username='admin' AND u.role='admin'
              AND NOT EXISTS (SELECT 1 FROM admins a WHERE a.user_id=u.user_id)
            LIMIT 1
            """
        )

        conn.commit()
        print("Schema updated successfully.")
    except Exception as exc:
        print(f"Error updating schema: {exc}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    update_schema_for_health_insights()
