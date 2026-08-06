from database import db
from werkzeug.security import generate_password_hash
import sys

def setup_custom_admin():
    """Prompts for a custom username and password to give admin rights"""
    print("\n--- Grant Application Admin Privileges ---")
    username = input("Enter username to grant admin rights: ").strip()
    password = input(f"Enter password for '{username}': ").strip()
    
    if not username or not password:
        print("❌ Username and password cannot be empty.")
        return

    # Check if user exists
    user = db.fetch_one("SELECT * FROM users WHERE username=%s", (username,))
    if user:
        print(f"❌ Error: The user '{username}' already exists. You cannot create a duplicate user.")
        return

    hashed_pw = generate_password_hash(password)
    db.execute("INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, 'admin', 1)", (username, hashed_pw))
    print(f"✅ New ADMIN user '{username}' created successfully.")

def grant_mysql_access():
    """Generates the SQL command to grant MySQL-level database access to a friend"""
    print("\n--- Grant MySQL Database Connection Access ---")
    friend_db_user = input("Enter your friend's MySQL username: ").strip()
    friend_db_pass = input(f"Enter a password for MySQL user '{friend_db_user}': ").strip()
    
    if not friend_db_user or not friend_db_pass:
        print("❌ MySQL username and password cannot be empty.")
        return

    db_name = "hospital_db"
    
    print(f"\n📋 COPY AND RUN THESE COMMANDS IN YOUR MYSQL TERMINAL (as root):")
    print(f"-------------------------------------------------------------")
    print(f"CREATE USER '{friend_db_user}'@'%' IDENTIFIED BY '{friend_db_pass}';")
    print(f"GRANT ALL PRIVILEGES ON {db_name}.* TO '{friend_db_user}'@'%';")
    print(f"FLUSH PRIVILEGES;")
    print(f"-------------------------------------------------------------")
    print(f"Note: '@'%' allows connection from any computer. If you only want local access, use '@'localhost'.")

def flush_database():
    """Clears all data from the database tables while preserving the structure"""
    print("\n--- Flush Database (Delete All Records) ---")
    confirm = input("⚠️ WARNING: This will delete ALL data from the database. Type 'yes' to confirm: ")
    if confirm.lower() != 'yes':
        print("❌ Database flush cancelled.")
        return

    tables = ['appointments', 'bills', 'patients', 'doctors', 'receptionist', 'feedback', 'admins', 'users']
    
    try:
        db.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in tables:
            # Check if table exists before truncating
            exists = db.fetch_one(f"SHOW TABLES LIKE '{table}'")
            if exists:
                db.execute(f"TRUNCATE TABLE {table}")
                print(f"🗑️  Flushed table: {table}")
        db.execute("SET FOREIGN_KEY_CHECKS = 1")
        print("\n✨ Database flushed successfully. All records removed.")
    except Exception as e:
        print(f"❌ Error during flush: {e}")
        db.execute("SET FOREIGN_KEY_CHECKS = 1")

if __name__ == "__main__":
    print("--- Medicare Hospital System Admin Setup ---")
    print("1. Grant App Admin Privileges (Application login)")
    print("2. Grant MySQL Database Access (Direct DB connection)")
    print("3. Flush Database (Delete all records)")
    print("4. Exit")
    
    choice = input("\nEnter choice (1-4): ")
    
    if choice == '1':
        setup_custom_admin()
    elif choice == '2':
        grant_mysql_access()
    elif choice == '3':
        flush_database()
    elif choice == '4':
        print("Exiting.")
    else:
        print("Invalid choice.")
