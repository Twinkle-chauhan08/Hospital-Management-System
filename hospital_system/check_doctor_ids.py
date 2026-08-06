from database import db

def check_doctor_ids():
    print("Checking Doctor IDs across tables...")
    
    doctors = db.fetch_all("SELECT doctor_id, name FROM doctors")
    for d in doctors:
        print(f"Doctor: {d['name']} | ID: {d['doctor_id']}")
        
        visit_count = db.fetch_one("SELECT COUNT(*) as c FROM visits WHERE doctor_id = %s", (d['doctor_id'],))
        appt_count = db.fetch_one("SELECT COUNT(*) as c FROM appointments WHERE doctor_id = %s", (d['doctor_id'],))
        
        print(f"  - Visits in 'visits' table for this ID: {visit_count['c']}")
        print(f"  - Appointments in 'appointments' table for this ID: {appt_count['c']}")

if __name__ == "__main__":
    check_doctor_ids()
