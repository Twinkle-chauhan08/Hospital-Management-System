from database import db

def check_counts():
    print("Checking database records for visit counts...")
    
    total_visits = db.fetch_one("SELECT COUNT(*) as c FROM visits")
    print(f"Total rows in 'visits' table: {total_visits['c']}")
    
    total_appointments = db.fetch_one("SELECT COUNT(*) as c FROM appointments")
    print(f"Total rows in 'appointments' table: {total_appointments['c']}")
    
    completed_appts = db.fetch_one("SELECT COUNT(*) as c FROM appointments WHERE status='Completed'")
    print(f"Total completed appointments: {completed_appts['c']}")
    
    patient_counts = db.fetch_all("""
        SELECT p.name, 
               (SELECT COUNT(*) FROM visits v JOIN appointments a ON v.appointment_id = a.appointment_id WHERE a.patient_id = p.patient_id) as v_count,
               (SELECT COUNT(*) FROM appointments a WHERE a.patient_id = p.patient_id AND a.status = 'Completed') as c_count
        FROM patients p
    """)
    
    for p in patient_counts:
        print(f"Patient: {p['name']} | Visits: {p['v_count']} | Completed Appts: {p['c_count']} | Total: {p['v_count'] + p['c_count']}")

if __name__ == "__main__":
    check_counts()
