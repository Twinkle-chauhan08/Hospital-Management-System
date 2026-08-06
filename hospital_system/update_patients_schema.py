import mysql.connector
from config import DevelopmentConfig as Config

def update_patients_table():
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        cursor = conn.cursor()
        print("Connected to database...")

        # --- Add missing columns to patients table ---
        columns_to_add = [
            ("address", "TEXT"),
            ("medical_history", "TEXT"),
            ("current_condition", "TEXT"),
            ("status", "VARCHAR(50) DEFAULT 'Pending'")
        ]

        for col_name, col_type in columns_to_add:
            print(f"Checking for column '{col_name}'...")
            cursor.execute(f"SHOW COLUMNS FROM patients LIKE '{col_name}'")
            if not cursor.fetchone():
                print(f"Adding column '{col_name}'...")
                cursor.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")
            else:
                print(f"Column '{col_name}' already exists.")

        conn.commit()
        print("Database schema updated successfully!")
        
    except Exception as e:
        print(f"Error updating database: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    update_patients_table()
