from database import Database

# Initialize database
db = Database()

# --------------------- USERS ---------------------
def add_user(username, password, role):
    # Check if user already exists
    existing = db.fetch_one("SELECT * FROM users WHERE username=%s", (username,))
    if existing:
        print(f"⚠️ User '{username}' already exists. Skipping.")
        return existing['user_id']
    
    query = "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)"
    db.execute_query(query, (username, password, role))
    user = db.fetch_one("SELECT * FROM users WHERE username=%s", (username,))
    print(f"✅ User '{username}' added.")
    return user['user_id']

# --------------------- DOCTORS ---------------------
def add_doctor(user_id, name, specialization, department, available=True):
    existing = db.fetch_one("SELECT * FROM doctors WHERE user_id=%s", (user_id,))
    if existing:
        print(f"⚠️ Doctor '{name}' already exists. Skipping.")
        return existing['doctor_id']
    
    query = """
        INSERT INTO doctors (user_id, name, specialization, department, available)
        VALUES (%s, %s, %s, %s, %s)
    """
    db.execute_query(query, (user_id, name, specialization, department, available))
    doctor = db.fetch_one("SELECT * FROM doctors WHERE user_id=%s", (user_id,))
    print(f"✅ Doctor '{name}' added.")
    return doctor['doctor_id']

# --------------------- PATIENTS ---------------------
def add_patient(user_id, name, age, gender, assigned_doctor_id=None, disease=None, blood_group=None, health_risk_level='Low'):
    existing = db.fetch_one("SELECT * FROM patients WHERE user_id=%s", (user_id,))
    if existing:
        print(f"⚠️ Patient '{name}' already exists. Skipping.")
        return existing['patient_id']
    
    query = """
        INSERT INTO patients (user_id, name, age, gender, assigned_doctor_id, disease, blood_group, health_risk_level)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    db.execute_query(query, (user_id, name, age, gender, assigned_doctor_id, disease, blood_group, health_risk_level))
    patient = db.fetch_one("SELECT * FROM patients WHERE user_id=%s", (user_id,))
    print(f"✅ Patient '{name}' added.")
    return patient['patient_id']

# --------------------- APPOINTMENTS ---------------------
def add_appointment(patient_id, doctor_id, appointment_date, appointment_time, status='Pending', reason=None, notes=None):
    query = """
        INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, status, reason_for_visit, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    db.execute_query(query, (patient_id, doctor_id, appointment_date, appointment_time, status, reason, notes))
    print(f"✅ Appointment added: patient_id={patient_id}, doctor_id={doctor_id}, {appointment_date} {appointment_time}")

# --------------------- EXAMPLE USAGE ---------------------
if __name__ == "__main__":
    from datetime import date, time

    # Add users
    user1_id = add_user("patient1", "patientpass", "patient")
    user2_id = add_user("doctor1", "doctorpass", "doctor")

    # Add doctor
    doctor1_id = add_doctor(user2_id, "Dr. Rajesh Kumar", "Cardiology", "Heart")

    # Add patient
    patient1_id = add_patient(user1_id, "Alice Johnson", 30, "Female", assigned_doctor_id=doctor1_id, disease="Hypertension", blood_group="A+", health_risk_level="Medium")

    # Add appointment
    add_appointment(patient1_id, doctor1_id, date(2026, 2, 15), time(10, 30), reason="Checkup", notes="First visit")
