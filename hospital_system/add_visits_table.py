import mysql.connector
from config import DevelopmentConfig as Config

def add_visits_table():
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME
        )
        cursor = conn.cursor()
        print("Connected to database...")

        # --- Create VISITS table ---
        print("Creating 'visits' table if it doesn't exist...")
        create_table_query = """
        CREATE TABLE IF NOT EXISTS visits (
            visit_id INT AUTO_INCREMENT PRIMARY KEY,
            appointment_id INT NOT NULL,
            doctor_id INT NOT NULL,
            visit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            progress_notes TEXT NOT NULL,
            FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
            FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE
        );
        """
        cursor.execute(create_table_query)
        
        conn.commit()
        print("Database schema updated successfully with 'visits' table!")
        
    except Exception as e:
        print(f"Error updating database: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    add_visits_table()
