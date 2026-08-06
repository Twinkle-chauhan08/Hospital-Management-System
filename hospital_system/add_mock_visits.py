from database import db
from datetime import datetime, timedelta

def add_mock_visits():
    print("Adding mock visits for all treated patients...")
    
    # Get all doctors
    doctors = db.fetch_all("SELECT doctor_id FROM doctors")
    
    for doc in doctors:
        doctor_id = doc['doctor_id']
        
        # Get all appointments for this doctor (to find patients they've interacted with)
        appointments = db.fetch_all("SELECT appointment_id, patient_id FROM appointments WHERE doctor_id = %s", (doctor_id,))
        
        # Group by patient to ensure we add visits for each
        patient_appointments = {}
        for appt in appointments:
            if appt['patient_id'] not in patient_appointments:
                patient_appointments[appt['patient_id']] = appt['appointment_id']
        
        for patient_id, appointment_id in patient_appointments.items():
            # Check current visit count
            existing_visits = db.fetch_one("SELECT COUNT(*) as count FROM visits WHERE appointment_id = %s", (appointment_id,))
            count = existing_visits['count'] if existing_visits else 0
            
            # If less than 4 visits, add more
            needed = 4 - count
            if needed > 0:
                print(f"Adding {needed} visits for Patient #{patient_id} (Appt #{appointment_id}) under Doctor #{doctor_id}")
                for i in range(needed):
                    visit_date = datetime.now() - timedelta(days=(needed-i)*2)
                    progress_notes = f"Follow-up visit {count + i + 1}. Patient showing improvement. Vital signs stable."
                    
                    db.execute("""
                        INSERT INTO visits (appointment_id, doctor_id, visit_date, progress_notes)
                        VALUES (%s, %s, %s, %s)
                    """, (appointment_id, doctor_id, visit_date, progress_notes))
    
    print("✅ Mock visits added successfully.")

if __name__ == "__main__":
    add_mock_visits()
