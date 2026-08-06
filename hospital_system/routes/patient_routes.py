import os
from datetime import datetime

from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename

from database import db, get_disease_to_doctor_mapping, get_advanced_health_insights
from routes.auth_routes import require_role

# Define the Blueprint
patient_bp = Blueprint('patient', __name__)

ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
APPOINTMENT_TIME_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00"
]
_slot_constraints_ready = False


def _ensure_appointment_slot_constraints():
    global _slot_constraints_ready
    if _slot_constraints_ready:
        return
    slot_col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'appointments'
          AND column_name = 'slot_active'
        LIMIT 1
    """)
    if not slot_col:
        db.execute("ALTER TABLE appointments ADD COLUMN slot_active TINYINT NULL DEFAULT 1")

    # Normalize any second-level times to minute precision used by booking slots.
    db.execute("""
        UPDATE appointments
        SET appointment_time = MAKETIME(HOUR(appointment_time), MINUTE(appointment_time), 0)
        WHERE appointment_time IS NOT NULL
          AND SECOND(appointment_time) <> 0
    """)

    # Backfill slot_active from status.
    db.execute("""
        UPDATE appointments
        SET slot_active = CASE
            WHEN status IN ('Pending', 'Confirmed') THEN 1
            ELSE NULL
        END
        WHERE slot_active IS NULL OR slot_active NOT IN (1)
    """)

    # Clean old duplicates: keep latest appointment active, cancel older duplicates.
    db.execute("""
        UPDATE appointments a
        JOIN (
            SELECT doctor_id,
                   appointment_date,
                   CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0')) AS slot_hhmm,
                   MAX(appointment_id) AS keep_id
            FROM appointments
            WHERE slot_active = 1
            GROUP BY doctor_id, appointment_date, CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0'))
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
    """)

    idx = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'appointments'
          AND index_name = 'uniq_active_doctor_slot'
        LIMIT 1
    """)
    if not idx:
        db.execute("""
            CREATE UNIQUE INDEX uniq_active_doctor_slot
            ON appointments (doctor_id, appointment_date, appointment_time, slot_active)
        """)
    _slot_constraints_ready = True


def _ensure_patient_profile_columns():
    required_columns = {
        'photo_path': "ALTER TABLE patients ADD COLUMN photo_path VARCHAR(255) NULL",
        'emergency_contact_name': "ALTER TABLE patients ADD COLUMN emergency_contact_name VARCHAR(100) NULL",
        'emergency_contact_phone': "ALTER TABLE patients ADD COLUMN emergency_contact_phone VARCHAR(15) NULL",
        'allergies': "ALTER TABLE patients ADD COLUMN allergies TEXT NULL"
    }

    for column_name, alter_sql in required_columns.items():
        col = db.fetch_one("""
            SELECT 1 AS c
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'patients'
              AND column_name = %s
            LIMIT 1
        """, (column_name,))
        if not col:
            db.execute(alter_sql)


def _is_allowed_profile_image(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def _save_patient_profile_photo(file_obj, patient_id):
    if not file_obj or not file_obj.filename:
        return None

    if not _is_allowed_profile_image(file_obj.filename):
        return "INVALID_FILE_TYPE"

    clean_name = secure_filename(file_obj.filename)
    extension = clean_name.rsplit('.', 1)[1].lower()
    unique_name = f"patient_{patient_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"

    # Always save into the real app static folder, regardless of the current working directory.
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'patient_profiles')
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, unique_name)
    file_obj.save(full_path)
    return f"uploads/patient_profiles/{unique_name}"


def _format_time_label(slot):
    hour = int(slot.split(':')[0])
    minute = slot.split(':')[1]
    suffix = 'AM' if hour < 12 else 'PM'
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute} {suffix}"


def _get_booked_slots(doctor_id, appointment_date):
    _ensure_appointment_slot_constraints()
    rows = db.fetch_all("""
        SELECT CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0')) AS slot
        FROM appointments
        WHERE doctor_id=%s
          AND appointment_date=%s
          AND slot_active = 1
    """, (doctor_id, appointment_date)) or []
    return [row['slot'] for row in rows if row.get('slot')]

# ================================
# Patient Dashboard
# ================================
@patient_bp.route('/patient_dashboard')
@require_role('patient')
def patient_dashboard():
    _ensure_patient_profile_columns()
    patient_id = session.get('patient_id')
    if not patient_id:
        return redirect(url_for('auth.login'))

    # Fetch patient info with assigned doctor
    patient = db.fetch_one("""
        SELECT p.*, d.name AS doctor_name, d.specialization AS doctor_specialization
        FROM patients p
        LEFT JOIN doctors d ON p.assigned_doctor_id = d.doctor_id
        WHERE p.patient_id=%s
    """, (patient_id,))

    # Fetch appointment stats
    appointment_stats = db.fetch_one("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending
        FROM appointments
        WHERE patient_id=%s
    """, (patient_id,))

    visits_done_row = db.fetch_one("""
        SELECT
            (SELECT COUNT(*)
             FROM visits v
             JOIN appointments a ON v.appointment_id = a.appointment_id
             WHERE a.patient_id=%s)
            +
            (SELECT COUNT(*)
             FROM appointments a
             WHERE a.patient_id=%s
               AND a.status='Completed'
               AND NOT EXISTS (
                    SELECT 1 FROM visits v2 WHERE v2.appointment_id = a.appointment_id
               )) AS c
    """, (patient_id, patient_id)) or {"c": 0}

    # Fetch notifications
    notifications = db.fetch_all("""
        SELECT * FROM notifications 
        WHERE user_id=%s AND is_read=FALSE
        ORDER BY created_at DESC
        LIMIT 5
    """, (session.get('user_id'),)) or []

    # Fetch recent medical history for progress tracker
    recent_history = db.fetch_all("""
        SELECT appointment_date, bp, weight, treatment
        FROM appointments
        WHERE patient_id=%s
          AND status IN ('Confirmed', 'Completed')
          AND (bp IS NOT NULL OR weight IS NOT NULL OR treatment IS NOT NULL)
        ORDER BY appointment_date DESC, appointment_time DESC
        LIMIT 5
    """, (patient_id,)) or []

    next_visit = db.fetch_one("""
        SELECT appointment_id, appointment_date, appointment_time, status, doctor_id
        FROM appointments
        WHERE patient_id=%s
          AND status IN ('Pending', 'Confirmed')
          AND appointment_date >= CURDATE()
        ORDER BY appointment_date ASC, appointment_time ASC
        LIMIT 1
    """, (patient_id,))

    latest_bill = db.fetch_one("""
        SELECT bill_id, appointment_id, total_amount, paid, payment_date
        FROM bills
        WHERE patient_id=%s
        ORDER BY bill_id DESC
        LIMIT 1
    """, (patient_id,))

    # Calculate total paid amount for all bills
    total_paid = db.fetch_one("""
        SELECT COALESCE(SUM(total_amount), 0) AS total_paid
        FROM bills
        WHERE patient_id=%s AND paid=1
    """, (patient_id,)) or {"total_paid": 0}

    return render_template(
        'patient_dashboard.html',
        patient=patient,
        appointments_count=appointment_stats['total'] or 0,
        visits_done_count=visits_done_row['c'] or 0,
        pending_appointments=appointment_stats['pending'] or 0,
        notifications=notifications,
        recent_history=recent_history,
        next_visit=next_visit,
        latest_bill=latest_bill,
        total_paid=total_paid
    )


@patient_bp.route('/patient_profile', methods=['GET', 'POST'])
@require_role('patient')
def patient_profile():
    _ensure_patient_profile_columns()
    patient_id = session.get('patient_id')

    if not patient_id:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        age = request.form.get('age')
        gender = (request.form.get('gender') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None
        blood_group = (request.form.get('blood_group') or '').strip() or None
        disease = (request.form.get('disease') or '').strip() or None
        address = (request.form.get('address') or '').strip() or None
        current_condition = (request.form.get('current_condition') or '').strip() or None
        medical_history = (request.form.get('medical_history') or '').strip() or None
        allergies = (request.form.get('allergies') or '').strip() or None
        emergency_contact_name = (request.form.get('emergency_contact_name') or '').strip() or None
        emergency_contact_phone = (request.form.get('emergency_contact_phone') or '').strip() or None

        if not all([name, age, gender]):
            flash("Name, age, and gender are required.", "danger")
            return redirect(url_for('patient.patient_profile'))

        try:
            age_value = int(age)
            if age_value <= 0:
                raise ValueError
        except ValueError:
            flash("Please enter a valid age.", "danger")
            return redirect(url_for('patient.patient_profile'))

        photo_file = request.files.get('profile_photo')
        photo_path = None
        if photo_file and photo_file.filename:
            photo_path = _save_patient_profile_photo(photo_file, patient_id)
            if photo_path == "INVALID_FILE_TYPE":
                flash("Please upload only PNG, JPG, JPEG, or WEBP image files.", "danger")
                return redirect(url_for('patient.patient_profile'))

        if photo_path:
            db.execute("""
                UPDATE patients
                SET name=%s,
                    age=%s,
                    gender=%s,
                    email=%s,
                    phone=%s,
                    blood_group=%s,
                    disease=%s,
                    address=%s,
                    current_condition=%s,
                    medical_history=%s,
                    allergies=%s,
                    emergency_contact_name=%s,
                    emergency_contact_phone=%s,
                    photo_path=%s
                WHERE patient_id=%s
            """, (
                name,
                age_value,
                gender,
                email,
                phone,
                blood_group,
                disease,
                address,
                current_condition,
                medical_history,
                allergies,
                emergency_contact_name,
                emergency_contact_phone,
                photo_path,
                patient_id
            ))
            flash("Profile photo uploaded successfully.", "success")
        else:
            db.execute("""
                UPDATE patients
                SET name=%s,
                    age=%s,
                    gender=%s,
                    email=%s,
                    phone=%s,
                    blood_group=%s,
                    disease=%s,
                    address=%s,
                    current_condition=%s,
                    medical_history=%s,
                    allergies=%s,
                    emergency_contact_name=%s,
                    emergency_contact_phone=%s
                WHERE patient_id=%s
            """, (
                name,
                age_value,
                gender,
                email,
                phone,
                blood_group,
                disease,
                address,
                current_condition,
                medical_history,
                allergies,
                emergency_contact_name,
                emergency_contact_phone,
                patient_id
            ))

        flash("Profile updated successfully.", "success")
        return redirect(url_for('patient.patient_profile'))

    patient = db.fetch_one("""
        SELECT p.*,
               u.username
        FROM patients p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.patient_id=%s
    """, (patient_id,))

    if not patient:
        flash("Patient profile not found.", "danger")
        return redirect(url_for('patient.patient_dashboard'))

    return render_template('patient_profile.html', patient=patient)


# ================================
# Book Appointment
# ================================
@patient_bp.route('/patient_book_appointment', methods=['GET', 'POST'])
@require_role('patient')
def book_appointment():
    _ensure_appointment_slot_constraints()
    patient_id = session.get('patient_id')
    if not patient_id:
        return redirect(url_for('auth.login'))

    patient = db.fetch_one(
        "SELECT disease FROM patients WHERE patient_id=%s",
        (patient_id,)
    ) or {}
    disease = (patient.get('disease') or '').strip().lower()

    recommended_specialization = None
    if disease:
        mapping = get_disease_to_doctor_mapping()
        for keyword, specialization in mapping.items():
            if keyword in disease:
                recommended_specialization = specialization
                break

    if recommended_specialization:
        doctors = db.fetch_all("""
            SELECT doctor_id, name, specialization
            FROM doctors
            WHERE available=TRUE
            ORDER BY CASE WHEN specialization=%s THEN 0 ELSE 1 END, name
        """, (recommended_specialization,)) or []
    else:
        doctors = db.fetch_all("""
            SELECT doctor_id, name, specialization
            FROM doctors
            WHERE available=TRUE
            ORDER BY name
        """) or []

    error = None
    form_data = {}
    initial_booked_slots = []

    if request.method == 'POST':
        form_data = request.form.to_dict()
        doctor_id = form_data.get('doctor_id')
        appointment_date = form_data.get('appointment_date')
        appointment_time = form_data.get('appointment_time')
        reason = form_data.get('reason', '').strip()

        if not doctor_id or not appointment_date or not appointment_time:
            error = "Please fill in all required fields."
        else:
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            current_hhmm = now.strftime('%H:%M')
            if appointment_date == today_str and appointment_time <= current_hhmm:
                error = "Selected time has already passed for today. Please choose a future time slot."
                return render_template(
                    'patient_book_appointment.html',
                    doctors=doctors,
                    recommended_specialization=recommended_specialization,
                    form_data=form_data,
                    error=error,
                    time_slots=APPOINTMENT_TIME_SLOTS,
                    initial_booked_slots=initial_booked_slots
                )

            occupied_slots = _get_booked_slots(doctor_id, appointment_date)
            if appointment_time in occupied_slots:
                error = "Selected time slot is no longer available. Please choose another time."
                initial_booked_slots = occupied_slots
                return render_template(
                    'patient_book_appointment.html',
                    doctors=doctors,
                    recommended_specialization=recommended_specialization,
                    form_data=form_data,
                    error=error,
                    time_slots=APPOINTMENT_TIME_SLOTS,
                    initial_booked_slots=initial_booked_slots
                )

            # Atomic insert to avoid race-condition double booking on same doctor/date/time.
            inserted = db.execute_query("""
                INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason_for_visit, status, slot_active)
                SELECT %s, %s, %s, %s, %s, 'Pending', 1
                FROM DUAL
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM appointments
                    WHERE doctor_id=%s
                      AND appointment_date=%s
                      AND CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0'))=%s
                      AND slot_active = 1
                )
            """, (
                patient_id,
                doctor_id,
                appointment_date,
                appointment_time,
                reason,
                doctor_id,
                appointment_date,
                appointment_time
            ))

            if not inserted:
                error = "Selected time slot was just booked by someone else. Please choose another time."
                initial_booked_slots = _get_booked_slots(doctor_id, appointment_date)
                return render_template(
                    'patient_book_appointment.html',
                    doctors=doctors,
                    recommended_specialization=recommended_specialization,
                    form_data=form_data,
                    error=error,
                    time_slots=APPOINTMENT_TIME_SLOTS,
                    initial_booked_slots=initial_booked_slots
                )

            # Get inserted appointment_id
            appt = db.fetch_one("""
                SELECT appointment_id
                FROM appointments
                WHERE patient_id=%s AND doctor_id=%s AND appointment_date=%s AND appointment_time=%s
                ORDER BY appointment_id DESC
                LIMIT 1
            """, (patient_id, doctor_id, appointment_date, appointment_time)) or {}
            appointment_id = appt.get('appointment_id')

            # Notify patient
            db.execute_query("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (session.get('user_id'), "Appointment request submitted. Waiting for confirmation.", "appointment", appointment_id))

            # Notify doctor
            doc = db.fetch_one("SELECT user_id, name FROM doctors WHERE doctor_id=%s", (doctor_id,))
            if doc and doc.get('user_id'):
                db.execute_query("""
                    INSERT INTO notifications (user_id, message, type, related_appointment_id)
                    VALUES (%s, %s, %s, %s)
                """, (doc['user_id'], "New pending appointment assigned to you.", "appointment", appointment_id))

            # Notify receptionist(s)
            receptionists = db.fetch_all("SELECT user_id FROM receptionist") or []
            for r in receptionists:
                if r.get('user_id'):
                    db.execute_query("""
                        INSERT INTO notifications (user_id, message, type, related_appointment_id)
                        VALUES (%s, %s, %s, %s)
                    """, (r['user_id'], "New appointment pending confirmation.", "appointment", appointment_id))

            # Assign doctor if patient has none
            patient = db.fetch_one("SELECT assigned_doctor_id FROM patients WHERE patient_id=%s", (patient_id,))
            if not patient['assigned_doctor_id']:
                db.execute_query(
                    "UPDATE patients SET assigned_doctor_id=%s WHERE patient_id=%s",
                    (doctor_id, patient_id)
                )
            return redirect(url_for('patient.view_appointments'))


    selected_doctor = form_data.get('doctor_id')
    selected_date = form_data.get('appointment_date')
    if selected_doctor and selected_date:
        initial_booked_slots = _get_booked_slots(selected_doctor, selected_date)

    return render_template(
        'patient_book_appointment.html',
        doctors=doctors,
        recommended_specialization=recommended_specialization,
        form_data=form_data,
        error=error,
        time_slots=APPOINTMENT_TIME_SLOTS,
        initial_booked_slots=initial_booked_slots
    )


@patient_bp.route('/doctor_available_slots')
@require_role('patient')
def doctor_available_slots():
    _ensure_appointment_slot_constraints()
    doctor_id = request.args.get('doctor_id')
    appointment_date = request.args.get('appointment_date')

    if not doctor_id or not appointment_date:
        return jsonify({"success": False, "message": "doctor_id and appointment_date are required."}), 400

    booked_slots = _get_booked_slots(doctor_id, appointment_date)
    slots = [
        {
            "value": slot,
            "label": _format_time_label(slot),
            "disabled": slot in booked_slots
        }
        for slot in APPOINTMENT_TIME_SLOTS
    ]
    return jsonify({"success": True, "slots": slots, "booked_slots": booked_slots})



# ================================
# View Appointments
# ================================
@patient_bp.route('/patient_appointments')
@require_role('patient')
def view_appointments():
    patient_id = session.get('patient_id')
    due_today_reminders = []
    appointments = db.fetch_all("""
        SELECT a.*,
               d.name AS doctor_name,
               d.specialization AS doctor_specialization,
               b.bill_id,
               COALESCE(b.total_amount, 0) AS bill_total_amount,
               b.paid AS bill_paid,
               b.payment_date AS bill_payment_date
        FROM appointments a
        LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
        LEFT JOIN bills b ON a.appointment_id = b.appointment_id
        WHERE a.patient_id=%s
        ORDER BY
            CASE
                WHEN a.status='Confirmed' AND a.appointment_date=CURDATE() THEN 0
                WHEN a.status IN ('Pending','Confirmed') AND a.appointment_date>CURDATE() THEN 1
                WHEN a.status='Pending' AND a.appointment_date=CURDATE() THEN 2
                WHEN a.status='Completed' THEN 3
                ELSE 4
            END,
            CASE WHEN a.appointment_date>=CURDATE() THEN a.appointment_date END ASC,
            CASE WHEN a.appointment_date>=CURDATE() THEN a.appointment_time END ASC,
            CASE WHEN a.appointment_date<CURDATE() THEN a.appointment_date END DESC,
            CASE WHEN a.appointment_date<CURDATE() THEN a.appointment_time END DESC
    """, (patient_id,)) or []

    # Fetch visits for each appointment
    for appt in appointments:
        appt['visits'] = db.fetch_all("""
            SELECT visit_date, progress_notes 
            FROM visits 
            WHERE appointment_id = %s 
            ORDER BY visit_date DESC
        """, (appt['appointment_id'],)) or []

        # Auto-create same-day reminder notification (once per day per appointment)
        if appt.get('status') == 'Confirmed':
            due_today = db.fetch_one("""
                SELECT 1 AS ok
                FROM appointments
                WHERE appointment_id=%s AND appointment_date=CURDATE()
                LIMIT 1
            """, (appt['appointment_id'],))
            if due_today:
                due_today_reminders.append({
                    'doctor_name': appt.get('doctor_name'),
                    'appointment_time': appt.get('appointment_time'),
                    'appointment_date': appt.get('appointment_date'),
                    'appointment_id': appt.get('appointment_id')
                })
                already_notified = db.fetch_one("""
                    SELECT notification_id
                    FROM notifications
                    WHERE user_id=%s
                      AND related_appointment_id=%s
                      AND type='visit_reminder'
                      AND DATE(created_at)=CURDATE()
                    LIMIT 1
                """, (session.get('user_id'), appt['appointment_id']))
                if not already_notified:
                    db.execute("""
                        INSERT INTO notifications (user_id, message, type, related_appointment_id)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        session.get('user_id'),
                        f"Today's visit reminder: Please visit Dr. {appt.get('doctor_name') or 'Doctor'} at {appt.get('appointment_time')}.",
                        "visit_reminder",
                        appt['appointment_id']
                    ))

    return render_template(
        'patient_appointments.html',
        appointments=appointments,
        due_today_reminders=due_today_reminders
    )


# ================================
# Cancel Appointment
# ================================
@patient_bp.route('/cancel_appointment/<int:appointment_id>', methods=['POST'])
@require_role('patient')
def cancel_appointment(appointment_id):
    patient_id = session.get('patient_id')
    
    # Verify appointment belongs to patient and is pending
    appt = db.fetch_one("""
        SELECT * FROM appointments 
        WHERE appointment_id=%s AND patient_id=%s AND status='Pending'
    """, (appointment_id, patient_id))
    
    if not appt:
        flash("Cannot cancel this appointment. It may already be confirmed or completed.", "danger")
        return redirect(url_for('patient.view_appointments'))
        
    # Update status
    db.execute("UPDATE appointments SET status='Cancelled', slot_active=NULL WHERE appointment_id=%s", (appointment_id,))
    
    # Notify doctor
    doctor = db.fetch_one("SELECT user_id FROM doctors WHERE doctor_id=%s", (appt['doctor_id'],))
    if doctor:
        db.execute("""
            INSERT INTO notifications (user_id, message, type, related_appointment_id)
            VALUES (%s, %s, %s, %s)
        """, (doctor['user_id'], f"Appointment #{appointment_id} was cancelled by the patient.", "cancellation", appointment_id))
        
    flash("Appointment cancelled successfully.", "success")
    return redirect(url_for('patient.view_appointments'))


# ================================
# Health Insights
# ================================
@patient_bp.route('/patient_health_insights')
@require_role('patient')
def health_insights():
    patient_id = session.get('patient_id')
    patient = db.fetch_one("""
        SELECT p.*, d.name AS doctor_name, d.specialization, d.phone
        FROM patients p
        LEFT JOIN doctors d ON p.assigned_doctor_id = d.doctor_id
        WHERE p.patient_id=%s
    """, (patient_id,))
    
    # Get computed health insights from patient history
    insights = get_advanced_health_insights(patient_id)
    
    return render_template('patient_health_insights.html', patient=patient, insights=insights)


# ================================
# View Bills
# ================================
@patient_bp.route('/patient_bills')
@require_role('patient')
def view_bills():
    patient_id = session.get('patient_id')
    selected_month = request.args.get('month', '')

    # Base query for bills
    base_query = """
        SELECT b.bill_id,
               b.appointment_id,
               a.appointment_date,
               a.appointment_time,
               b.consultation_fee,
               b.treatment_cost,
               b.medicines_cost,
               b.total_amount,
               b.paid,
               b.payment_date,
               MONTH(a.appointment_date) AS bill_month,
               YEAR(a.appointment_date) AS bill_year
        FROM bills b
        JOIN appointments a ON b.appointment_id = a.appointment_id
        WHERE b.patient_id=%s
    """

    params = [patient_id]

    # Filter by month if selected
    if selected_month:
        try:
            year, month = selected_month.split('-')
            base_query += " AND YEAR(a.appointment_date) = %s AND MONTH(a.appointment_date) = %s"
            params.extend([year, month])
        except ValueError:
            pass  # Invalid format, ignore filter

    base_query += " ORDER BY b.bill_id DESC"

    bills = db.fetch_all(base_query, tuple(params)) or []
    
    # Calculate total_amount in Python, convert all Decimals to float to avoid type errors
    for bill in bills:
        # Convert each fee to float, default to 0.0 if None
        cf = float(bill['consultation_fee']) if bill['consultation_fee'] is not None else 0.0
        tc = float(bill['treatment_cost']) if bill['treatment_cost'] is not None else 0.0
        mc = float(bill['medicines_cost']) if bill['medicines_cost'] is not None else 0.0
        bill['consultation_fee'] = cf
        bill['treatment_cost'] = tc
        bill['medicines_cost'] = mc
        bill['total_amount'] = cf + tc + mc
    
    # Calculate monthly total in Python using the bills we already have (most reliable!)
    calculated_monthly_total = 0.0
    for bill in bills:
        calculated_monthly_total += bill['total_amount']

    # Generate month dropdown options and display label
    current_date = datetime.now()
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_options = []
    for i in range(12):
        month_num = ((current_date.month - i - 1) % 12) + 1
        year = current_date.year - (1 if current_date.month - i <= 0 else 0)
        month_code = f"{year:04d}-{month_num:02d}"
        month_options.append((month_code, f"{month_names[month_num - 1]} {year}"))

    if selected_month:
        selected_month_label = next((label for code, label in month_options if code == selected_month), None)
        if not selected_month_label:
            selected_month_label = selected_month
    else:
        selected_month_label = f"Current Month ({month_names[current_date.month - 1]} {current_date.year})"
    
    # Use the Python-calculated monthly total (most accurate!)
    monthly_total = {"monthly_total": calculated_monthly_total}

    return render_template(
        'patient_bills.html',
        bills=bills,
        selected_month=selected_month,
        selected_month_label=selected_month_label,
        monthly_total=monthly_total,
        month_options=month_options
    )


# ================================
# E-Prescriptions
# ================================
@patient_bp.route('/patient_prescriptions')
@require_role('patient')
def patient_prescriptions():
    patient_id = session.get('patient_id')
    prescriptions = db.fetch_all("""
        SELECT a.appointment_id,
               a.appointment_date,
               a.appointment_time,
               a.prescription,
               a.treatment,
               a.bp,
               a.weight,
               a.next_visit_date,
               d.name AS doctor_name,
               d.specialization AS doctor_specialization
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_id=%s AND a.status='Completed'
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (patient_id,)) or []

    return render_template('patient_prescriptions.html', prescriptions=prescriptions)


@patient_bp.route('/patient_prescriptions/<int:appointment_id>')
@require_role('patient')
def patient_prescription_view(appointment_id):
    patient_id = session.get('patient_id')

    prescription = db.fetch_one("""
        SELECT a.appointment_id,
               a.appointment_date,
               a.appointment_time,
               a.prescription,
               a.treatment,
               a.bp,
               a.weight,
               a.next_visit_date,
               p.name AS patient_name,
               p.age,
               p.gender,
               d.name AS doctor_name,
               d.specialization AS doctor_specialization
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s AND a.patient_id=%s AND a.status='Completed'
    """, (appointment_id, patient_id))

    if not prescription:
        flash("Prescription not found.", "danger")
        return redirect(url_for('patient.patient_prescriptions'))

    return render_template('patient_prescription_view.html', rx=prescription)
