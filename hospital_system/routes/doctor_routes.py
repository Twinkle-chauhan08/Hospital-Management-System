from datetime import date, datetime

import os

from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app, jsonify
from werkzeug.utils import secure_filename
from database import db
from routes.auth_routes import require_role

doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')

ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

APPOINTMENT_TIME_SLOTS = [
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00"
]


def _format_time_label(slot):
    hour = int(slot.split(':')[0])
    minute = slot.split(':')[1]
    suffix = 'AM' if hour < 12 else 'PM'
    display_hour = hour % 12 or 12
    return f"{display_hour}:{minute} {suffix}"


def _get_booked_slots(doctor_id, appointment_date):
    rows = db.fetch_all("""
        SELECT CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0')) AS slot
        FROM appointments
        WHERE doctor_id=%s
          AND appointment_date=%s
          AND status IN ('Pending', 'Confirmed')
    """, (doctor_id, appointment_date)) or []
    return [row['slot'] for row in rows if row.get('slot')]


def _normalize_filter_date(raw_date):
    text = (raw_date or '').strip()
    if not text:
        return date.today()

    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return date.today()


def _redirect_back_to_filtered_appointments():
    selected_date = request.form.get('return_date') or request.args.get('date')
    view_mode = request.form.get('return_view') or request.args.get('view') or 'all'
    if selected_date:
        return redirect(url_for('doctor.doctor_appointments', date=selected_date, view=view_mode))
    return redirect(url_for('doctor.doctor_appointments', view=view_mode))


def _ensure_doctor_profile_columns():
    col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'doctors'
          AND column_name = 'qualification'
        LIMIT 1
    """)
    if not col:
        db.execute("ALTER TABLE doctors ADD COLUMN qualification VARCHAR(150) NULL")

    photo_col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'doctors'
          AND column_name = 'photo_path'
        LIMIT 1
    """)
    if not photo_col:
        db.execute("ALTER TABLE doctors ADD COLUMN photo_path VARCHAR(255) NULL")


def _is_allowed_profile_image(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def _save_doctor_profile_photo(file_obj, doctor_id):
    if not file_obj or not file_obj.filename:
        return None
    if not _is_allowed_profile_image(file_obj.filename):
        return "INVALID_FILE_TYPE"

    clean_name = secure_filename(file_obj.filename)
    extension = clean_name.rsplit('.', 1)[1].lower()
    unique_name = f"doctor_{doctor_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'doctor_profiles')
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, unique_name)
    file_obj.save(full_path)
    return f"uploads/doctor_profiles/{unique_name}"


# ===================== DOCTOR DASHBOARD =====================
@doctor_bp.route('/dashboard')
@require_role('doctor')
def doctor_dashboard():
    _ensure_doctor_profile_columns()

    doctor_id = session.get('doctor_id')

    if not doctor_id:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('auth.login'))

    # Total Assigned Patients
    patient_row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM patients WHERE assigned_doctor_id=%s",
        (doctor_id,)
    ) or {"c": 0}

    # Total Pending Appointments
    pending_row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM appointments WHERE doctor_id=%s AND status='Pending'",
        (doctor_id,)
    ) or {"c": 0}

    # Total consultations overall
    visits_row = db.fetch_one("""
        SELECT 
            (SELECT COUNT(*) FROM visits WHERE doctor_id=%s) +
            (SELECT COUNT(*)
             FROM appointments a
             WHERE a.doctor_id=%s
               AND a.status='Completed'
               AND NOT EXISTS (
                    SELECT 1
                    FROM visits v
                    WHERE v.appointment_id = a.appointment_id
                      AND v.doctor_id = a.doctor_id
               )) AS c
    """, (doctor_id, doctor_id)) or {"c": 0}

    # Fetch recent notifications for the doctor
    notifications = db.fetch_all("""
        SELECT notification_id, message, type, created_at
        FROM notifications
        WHERE user_id = (SELECT user_id FROM doctors WHERE doctor_id = %s)
        ORDER BY created_at DESC
        LIMIT 10
    """, (doctor_id,)) or []

    return render_template(
        'doctor_dashboard.html',
        patients_count=patient_row['c'],
        pending_count=pending_row['c'],
        visits_count=visits_row['c'],
        notifications=notifications
    )


@doctor_bp.route('/available_slots')
@require_role('doctor')
def doctor_available_slots():
    doctor_id = session.get('doctor_id')
    appointment_date = request.args.get('appointment_date')

    if not doctor_id or not appointment_date:
        return jsonify({"success": False, "message": "doctor_id and appointment_date are required."}), 400

    booked_slots = _get_booked_slots(doctor_id, appointment_date)
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    current_hhmm = now.strftime('%H:%M')
    slots = [
        {
            "value": slot,
            "label": _format_time_label(slot),
            "disabled": (slot in booked_slots) or (appointment_date == today_str and slot < current_hhmm)
        }
        for slot in APPOINTMENT_TIME_SLOTS
    ]
    return jsonify({"success": True, "slots": slots, "booked_slots": booked_slots})


@doctor_bp.route('/profile', methods=['GET', 'POST'])
@require_role('doctor')
def doctor_profile():
    _ensure_doctor_profile_columns()
    doctor_id = session.get('doctor_id')

    if not doctor_id:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        qualification = (request.form.get('qualification') or '').strip() or None
        specialization = (request.form.get('specialization') or '').strip()
        department = (request.form.get('department') or '').strip()
        experience_years = request.form.get('experience_years')
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None
        available = 1 if request.form.get('available') == 'on' else 0

        photo_file = request.files.get('profile_photo')
        photo_path = None
        if photo_file and photo_file.filename:
            photo_path = _save_doctor_profile_photo(photo_file, doctor_id)
            if photo_path == "INVALID_FILE_TYPE":
                flash("Please upload only PNG, JPG, JPEG, or WEBP image files.", "danger")
                return redirect(url_for('doctor.doctor_profile'))

        if name.lower().startswith('dr. '):
            name = name[4:].strip()

        if not all([name, specialization, department]):
            flash("Name, specialization and department are required.", "danger")
            return redirect(url_for('doctor.doctor_profile'))

        if photo_path:
            db.execute("""
                UPDATE doctors
                SET name=%s,
                    qualification=%s,
                    specialization=%s,
                    department=%s,
                    experience_years=%s,
                    email=%s,
                    phone=%s,
                    available=%s,
                    photo_path=%s
                WHERE doctor_id=%s
            """, (
                name,
                qualification,
                specialization,
                department,
                int(experience_years) if experience_years else None,
                email,
                phone,
                available,
                photo_path,
                doctor_id
            ))
            flash("Profile photo uploaded successfully.", "success")
        else:
            db.execute("""
                UPDATE doctors
                SET name=%s,
                    qualification=%s,
                    specialization=%s,
                    department=%s,
                    experience_years=%s,
                    email=%s,
                    phone=%s,
                    available=%s
                WHERE doctor_id=%s
            """, (
                name,
                qualification,
                specialization,
                department,
                int(experience_years) if experience_years else None,
                email,
                phone,
                available,
                doctor_id
            ))

        flash("Profile updated successfully.", "success")
        return redirect(url_for('doctor.doctor_profile'))

    doctor = db.fetch_one("""
        SELECT d.doctor_id, d.user_id, d.name, d.qualification, d.specialization, d.department,
               d.experience_years, d.email, d.phone, d.available, d.photo_path, u.username
        FROM doctors d
        JOIN users u ON d.user_id = u.user_id
        WHERE d.doctor_id=%s
    """, (doctor_id,))

    if not doctor:
        flash("Doctor profile not found.", "danger")
        return redirect(url_for('doctor.doctor_dashboard'))

    return render_template('doctor_profile.html', doctor=doctor)


# ===================== DOCTOR PATIENT LIST =====================
@doctor_bp.route('/patients')
@require_role('doctor')
def doctor_patients():

    doctor_id = session.get('doctor_id')
    search_query = (request.args.get('q') or '').strip()

    where_clause = """
        (p.assigned_doctor_id=%s OR p.patient_id IN (SELECT DISTINCT patient_id FROM appointments WHERE doctor_id=%s))
    """
    params = [doctor_id, doctor_id, doctor_id, doctor_id]
    if search_query:
        where_clause += " AND p.name LIKE %s "
        params.append(f"%{search_query}%")

    patients = db.fetch_all(f"""
        SELECT p.patient_id, p.name, p.age, p.gender, p.disease,
               p.health_risk_level, p.blood_group, p.status,
               p.phone, p.email, p.current_condition, p.medical_history, p.address,
               (SELECT COUNT(*) FROM visits v JOIN appointments a ON v.appointment_id = a.appointment_id WHERE a.patient_id = p.patient_id AND a.doctor_id = %s) +
               (SELECT COUNT(*) FROM appointments a WHERE a.patient_id = p.patient_id AND a.status = 'Completed' AND a.doctor_id = %s) AS visit_count
        FROM patients p
        WHERE {where_clause}
        ORDER BY p.patient_id DESC
    """, tuple(params)) or []

    # Fetch detailed history for each patient (visits and completed appointments)
    for p in patients:
        # Fetch visits
        p['visits'] = db.fetch_all("""
            SELECT v.visit_date, v.progress_notes, a.appointment_date, a.appointment_time
            FROM visits v
            JOIN appointments a ON v.appointment_id = a.appointment_id
            WHERE a.patient_id = %s AND a.doctor_id = %s
            ORDER BY v.visit_date DESC
        """, (p['patient_id'], doctor_id)) or []
        
        # Fetch completed appointments with treatment details
        p['completed_appointments'] = db.fetch_all("""
            SELECT appointment_date, bp, weight, prescription, treatment, next_visit_date
            FROM appointments
            WHERE patient_id = %s AND doctor_id = %s AND status = 'Completed'
            ORDER BY appointment_date DESC
        """, (p['patient_id'], doctor_id)) or []

    return render_template('doctor_patients.html', patients=patients, search_query=search_query)


# ===================== UPDATE PATIENT CONDITION & STATUS =====================
@doctor_bp.route('/update_patient_info/<int:patient_id>', methods=['POST'])
@require_role('doctor')
def update_patient_info(patient_id):

    doctor_id = session.get('doctor_id')
    new_status = request.form.get('status')
    new_condition = request.form.get('current_condition', '').strip()
    new_history = request.form.get('medical_history', '').strip()
    new_address = request.form.get('address', '').strip()

    patient = db.fetch_one(
        "SELECT patient_id FROM patients WHERE patient_id=%s AND assigned_doctor_id=%s",
        (patient_id, doctor_id)
    )
    if not patient:
        flash("You can only update info for your own assigned patients.", "danger")
        return redirect(url_for('doctor.doctor_patients'))

    db.execute("""
        UPDATE patients
        SET status=%s, current_condition=%s, medical_history=%s, address=%s
        WHERE patient_id=%s AND assigned_doctor_id=%s
    """, (new_status or 'Under Treatment', new_condition, new_history, new_address, patient_id, doctor_id))

    flash("Patient information updated successfully!", "success")
    return redirect(url_for('doctor.doctor_patients'))


# ===================== DOCTOR PATIENT HISTORY =====================
@doctor_bp.route('/patient_history/<int:patient_id>')
@require_role('doctor')
def patient_history(patient_id):
    doctor_id = session.get('doctor_id')
    
    # Verify patient is assigned to this doctor
    patient = db.fetch_one("""
        SELECT * FROM patients 
        WHERE patient_id=%s AND assigned_doctor_id=%s
    """, (patient_id, doctor_id))
    
    if not patient:
        flash("You can only view history for your assigned patients.", "danger")
        return redirect(url_for('doctor.doctor_patients'))

    # Fetch all appointments for this patient and assign visit numbers
    all_appointments = db.fetch_all("""
        SELECT a.*, d.name AS doctor_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.patient_id=%s
        ORDER BY a.appointment_date ASC, a.appointment_time ASC
    """, (patient_id,))
    
    # Fetch all visits for this patient
    visits = db.fetch_all("""
        SELECT v.visit_id, v.appointment_id, v.visit_date, v.progress_notes
        FROM visits v
        JOIN appointments a ON v.appointment_id = a.appointment_id
        WHERE a.patient_id=%s
        ORDER BY v.visit_date ASC
    """, (patient_id,))

    # Combine appointments and visits into a single history timeline
    history = []
    for appt in all_appointments:
        history.append({
            'type': 'appointment',
            'date': appt['appointment_date'],
            'time': appt['appointment_time'],
            'data': appt
        })
    for visit in visits:
        history.append({
            'type': 'visit',
            'date': visit['visit_date'].date(),
            'time': visit['visit_date'].time(),
            'data': visit
        })

    # Sort history by date and time
    history.sort(key=lambda x: (x['date'], x['time']), reverse=True)

    # Assign visit numbers
    visit_num = 0
    for item in reversed(history):
        if item['type'] == 'appointment' and item['data']['status'] == 'Completed':
            visit_num += 1
            item['visit_no'] = visit_num
        elif item['type'] == 'visit':
            visit_num += 1
            item['visit_no'] = visit_num
        else:
            item['visit_no'] = None

    # Fetch medical records/bills
    bills = db.fetch_all("""
        SELECT * FROM bills 
        WHERE patient_id=%s 
        ORDER BY bill_id DESC
    """, (patient_id,))

    return render_template(
        'doctor_patient_history.html',
        patient=patient,
        history=history,
        bills=bills
    )


# ===================== DOCTOR APPOINTMENTS =====================
@doctor_bp.route('/appointments')
@require_role('doctor')
def doctor_appointments():

    doctor_id = session.get('doctor_id')
    selected_date_obj = _normalize_filter_date(request.args.get('date'))
    selected_date = selected_date_obj.isoformat()
    view_mode = (request.args.get('view') or 'remaining').strip().lower()
    if view_mode not in ('completed', 'visited', 'remaining'):
        view_mode = 'remaining'

    # Backfill/sync old follow-up records created before the new date+time flow:
    # if a visit exists and next_visit_date was set, keep appointment_date aligned.
    db.execute("""
        UPDATE appointments a
        SET a.appointment_date = a.next_visit_date
        WHERE a.doctor_id=%s
          AND a.status IN ('Pending', 'Confirmed')
          AND a.next_visit_date IS NOT NULL
          AND a.appointment_date <> a.next_visit_date
          AND EXISTS (
              SELECT 1
              FROM visits v
              WHERE v.appointment_id = a.appointment_id
                AND v.doctor_id = a.doctor_id
          )
    """, (doctor_id,))

    mode_clause = ""
    date_clause = " AND a.appointment_date=%s "
    if view_mode == 'completed':
        mode_clause = " AND a.status='Completed' "
    elif view_mode == 'visited':
        date_clause = " AND a.next_visit_date=%s "
        mode_clause = """
            AND a.status IN ('Pending', 'Confirmed')
            AND EXISTS (
                SELECT 1 FROM visits v
                WHERE v.appointment_id = a.appointment_id
                  AND v.doctor_id = a.doctor_id
            )
            AND a.next_visit_date IS NOT NULL
        """
    else:
        mode_clause = """
            AND a.status IN ('Pending', 'Confirmed')
            AND NOT EXISTS (
                SELECT 1 FROM visits v
                WHERE v.appointment_id = a.appointment_id
                  AND v.doctor_id = a.doctor_id
            )
        """

    appointments = db.fetch_all(f"""
    SELECT a.appointment_id,
           a.appointment_date,
           a.appointment_time,
           a.status,
           a.next_visit_date,
           a.reason_for_visit,
           p.name AS patient_name,
           p.disease,
           CASE WHEN DATE(COALESCE(a.next_visit_date, a.appointment_date)) > CURDATE() THEN 1 ELSE 0 END AS is_future,
           EXISTS(
               SELECT 1
               FROM visits v
               WHERE v.appointment_id = a.appointment_id
                 AND v.doctor_id = a.doctor_id
                 AND DATE(v.visit_date) = DATE(%s)
           ) AS visit_logged_for_selected_date
    FROM appointments a
    JOIN patients p ON a.patient_id = p.patient_id
    WHERE a.doctor_id=%s
      {date_clause}
      {mode_clause}
    ORDER BY a.appointment_time ASC
    """, (selected_date, doctor_id, selected_date)) or []

    counts = db.fetch_one("""
        SELECT
            SUM(CASE WHEN a.status='Completed' AND a.appointment_date=%s THEN 1 ELSE 0 END) AS completed_count,
            SUM(
                CASE
                    WHEN a.status IN ('Pending', 'Confirmed')
                     AND a.next_visit_date=%s
                     AND EXISTS (
                        SELECT 1
                        FROM visits v
                        WHERE v.appointment_id = a.appointment_id
                          AND v.doctor_id = a.doctor_id
                     )
                     AND a.next_visit_date IS NOT NULL
                    THEN 1 ELSE 0
                END
            ) AS visited_count,
            SUM(
                CASE
                    WHEN a.status IN ('Pending', 'Confirmed')
                     AND a.appointment_date=%s
                     AND NOT EXISTS (
                        SELECT 1
                        FROM visits v
                        WHERE v.appointment_id = a.appointment_id
                          AND v.doctor_id = a.doctor_id
                     )
                    THEN 1 ELSE 0
                END
            ) AS remaining_count
        FROM appointments a
        WHERE a.doctor_id=%s
    """, (selected_date, selected_date, selected_date, doctor_id)) or {}


    return render_template(
        'doctor_appointments.html',
        appointments=appointments,
        selected_date=selected_date,
        view_mode=view_mode,
        completed_count=counts.get('completed_count') or 0,
        visited_count=counts.get('visited_count') or 0,
        remaining_count=counts.get('remaining_count') or 0,
        today_date=date.today().isoformat()
    )


# ===================== VIEW PATIENT DETAILS =====================
@doctor_bp.route('/view_patient/<int:patient_id>')
@require_role('doctor')
def doctor_view_patient(patient_id):
    doctor_id = session.get('doctor_id')

    patient = db.fetch_one("""
        SELECT *
        FROM patients
        WHERE patient_id=%s AND assigned_doctor_id=%s
    """, (patient_id, doctor_id))

    if not patient:
        flash("Patient not found or not assigned to you.", "danger")
        return redirect(url_for('doctor.doctor_patients'))

    appointments = db.fetch_all("""
        SELECT appointment_id, appointment_date, appointment_time, status, reason_for_visit
        FROM appointments
        WHERE patient_id=%s AND doctor_id=%s
        ORDER BY appointment_date DESC, appointment_time DESC
    """, (patient_id, doctor_id)) or []

    return render_template('doctor_patient_details.html', patient=patient, appointments=appointments)


@doctor_bp.route('/appointments/<int:appointment_id>/confirm', methods=['POST'])
@require_role('doctor')
def confirm_appointment(appointment_id):
    doctor_id = session.get('doctor_id')
    
    updated = db.execute("""
        UPDATE appointments
        SET status='Confirmed', slot_active=1
        WHERE appointment_id=%s AND doctor_id=%s AND status='Pending'
    """, (appointment_id, doctor_id))
    
    if updated:
        # Notify patient
        appt = db.fetch_one("""
            SELECT a.appointment_id, p.user_id AS patient_user_id, d.name AS doctor_name
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            JOIN doctors d ON a.doctor_id = d.doctor_id
            WHERE a.appointment_id=%s
        """, (appointment_id,))
        
        if appt and appt.get('patient_user_id'):
            message = f"Your appointment with Dr. {appt['doctor_name']} has been confirmed."
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['patient_user_id'], message, "appointment", appointment_id))
            
        flash("Appointment confirmed successfully!", "success")
    else:
        flash("Unable to confirm appointment.", "danger")
        
    return _redirect_back_to_filtered_appointments()


# ===================== E-PRESCRIPTIONS =====================
@doctor_bp.route('/prescriptions')
@require_role('doctor')
def doctor_prescriptions():
    doctor_id = session.get('doctor_id')

    prescriptions = db.fetch_all("""
        SELECT a.appointment_id,
               a.appointment_date,
               a.appointment_time,
               a.status,
               a.prescription,
               a.treatment,
               a.bp,
               a.weight,
               a.next_visit_date,
               p.patient_id,
               p.name AS patient_name,
               p.age,
               p.gender
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        WHERE a.doctor_id=%s AND a.status='Completed'
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (doctor_id,)) or []

    return render_template('doctor_prescriptions.html', prescriptions=prescriptions)


@doctor_bp.route('/prescriptions/<int:appointment_id>', methods=['GET', 'POST'])
@require_role('doctor')
def edit_prescription(appointment_id):
    doctor_id = session.get('doctor_id')

    appt = db.fetch_one("""
        SELECT a.appointment_id,
               a.appointment_date,
               a.appointment_time,
               a.status,
               a.prescription,
               a.treatment,
               a.bp,
               a.weight,
               a.next_visit_date,
               p.patient_id,
               p.name AS patient_name,
               p.age,
               p.gender,
               p.user_id AS patient_user_id
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        WHERE a.appointment_id=%s AND a.doctor_id=%s AND a.status='Completed'
    """, (appointment_id, doctor_id))

    if not appt:
        flash("Prescription record not found for this completed appointment.", "danger")
        return redirect(url_for('doctor.doctor_prescriptions'))

    if request.method == 'POST':
        prescription = (request.form.get('prescription') or '').strip()
        treatment = (request.form.get('treatment') or '').strip()
        bp = (request.form.get('bp') or '').strip()
        weight = (request.form.get('weight') or '').strip()
        next_visit_date = request.form.get('next_visit_date') or None

        if not prescription:
            flash("Prescription cannot be empty.", "danger")
            return render_template('doctor_edit_prescription.html', appt=appt)

        db.execute("""
            UPDATE appointments
            SET prescription=%s,
                treatment=%s,
                bp=%s,
                weight=%s,
                next_visit_date=%s
            WHERE appointment_id=%s AND doctor_id=%s AND status='Completed'
        """, (prescription, treatment, bp, weight, next_visit_date, appointment_id, doctor_id))

        if appt.get('patient_user_id'):
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['patient_user_id'], "Your e-prescription has been updated by your doctor.", "prescription", appointment_id))

        flash("E-prescription updated successfully.", "success")
        return redirect(url_for('doctor.edit_prescription', appointment_id=appointment_id))

    return render_template('doctor_edit_prescription.html', appt=appt)


@doctor_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@require_role('doctor')
def cancel_appointment(appointment_id):
    doctor_id = session.get('doctor_id')
    
    updated = db.execute("""
        UPDATE appointments
        SET status='Cancelled', slot_active=NULL
        WHERE appointment_id=%s AND doctor_id=%s AND status IN ('Pending', 'Confirmed')
    """, (appointment_id, doctor_id))
    
    if updated:
        flash("Appointment cancelled successfully.", "info")
    else:
        flash("Unable to cancel appointment.", "danger")
        
    return _redirect_back_to_filtered_appointments()


@doctor_bp.route('/appointments/<int:appointment_id>/add_visit', methods=['POST'])
@require_role('doctor')
def add_visit(appointment_id):
    doctor_id = session.get('doctor_id')
    prescription = request.form.get('prescription', '').strip()
    treatment = request.form.get('treatment', '').strip()
    bp = request.form.get('bp', '').strip()
    weight = request.form.get('weight', '').strip()
    next_visit_date = request.form.get('next_visit_date')
    next_visit_time = request.form.get('next_visit_time')
    report_needed = request.form.getlist('report_needed')
    report_other = (request.form.get('report_other') or '').strip()

    if not all([prescription, treatment, bp, weight, next_visit_date, next_visit_time]):
        flash("Please fill all visit fields. Next visit date and time are mandatory.", "danger")
        return _redirect_back_to_filtered_appointments()

    if report_other:
        report_needed.append(report_other)

    slot_conflict = db.fetch_one("""
        SELECT appointment_id
        FROM appointments
        WHERE doctor_id=%s
          AND appointment_id<>%s
          AND appointment_date=%s
          AND CONCAT(LPAD(HOUR(appointment_time), 2, '0'), ':', LPAD(MINUTE(appointment_time), 2, '0'))=%s
          AND status IN ('Pending', 'Confirmed')
        LIMIT 1
    """, (doctor_id, appointment_id, next_visit_date, next_visit_time))
    if slot_conflict:
        flash("Selected next visit slot is already booked. Please choose a different date/time.", "danger")
        return _redirect_back_to_filtered_appointments()

    # Verify appointment belongs to doctor and is confirmed OR pending (allow visiting if they showed up)
    appt = db.fetch_one("""
        SELECT a.appointment_id, a.patient_id, a.status, p.user_id AS patient_user_id, p.name AS patient_name, d.name AS doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s AND a.doctor_id=%s AND a.status IN ('Confirmed', 'Pending')
    """, (appointment_id, doctor_id))

    if not appt:
        flash("Invalid appointment or status.", "danger")
        return _redirect_back_to_filtered_appointments()

    future_block = db.fetch_one("""
        SELECT 1 AS blocked
        FROM appointments
        WHERE appointment_id=%s
          AND doctor_id=%s
          AND DATE(COALESCE(next_visit_date, appointment_date)) > CURDATE()
        LIMIT 1
    """, (appointment_id, doctor_id))
    if future_block:
        flash("You cannot enter visit details before the actual scheduled date.", "danger")
        return _redirect_back_to_filtered_appointments()

    # If it was pending, auto-confirm it since the patient is here
    if appt.get('status') == 'Pending':
        db.execute("UPDATE appointments SET status='Confirmed', slot_active=1 WHERE appointment_id=%s", (appointment_id,))

    reports_text = ", ".join(report_needed) if report_needed else "No additional reports required"
    visit_details = (
        f"Treatment: {treatment}\n"
        f"BP: {bp}\n"
        f"Weight: {weight}\n"
        f"Prescription: {prescription}\n"
        f"Next Visit Date: {next_visit_date}\n"
        f"Next Visit Time: {next_visit_time}\n"
        f"Recommended Reports: {reports_text}"
    )

    # Insert visit record
    db.execute("""
        INSERT INTO visits (appointment_id, doctor_id, progress_notes)
        VALUES (%s, %s, %s)
    """, (appointment_id, doctor_id, visit_details))

    # Notify doctor about scheduled next visit
    db.execute("""
        INSERT INTO notifications (user_id, message, type, related_appointment_id)
        VALUES ((SELECT user_id FROM doctors WHERE doctor_id = %s), %s, %s, %s)
    """, (doctor_id, f"Next visit for {appt['patient_name']} scheduled on {next_visit_date} at {next_visit_time}.", "reminder", appointment_id))

    # Save current visit details to appointment (before final completion)
    db.execute("""
        UPDATE appointments
        SET treatment=%s,
            bp=%s,
            weight=%s,
            prescription=%s,
            next_visit_date=%s,
            notes=%s,
            appointment_date=%s,
            appointment_time=%s,
            status='Confirmed',
            slot_active=1
        WHERE appointment_id=%s AND doctor_id=%s
    """, (
        treatment,
        bp,
        weight,
        prescription,
        next_visit_date,
        f"Recommended Reports: {reports_text}",
        next_visit_date,
        next_visit_time,
        appointment_id,
        doctor_id
    ))

    # Update patient status to "Under Treatment"
    db.execute("UPDATE patients SET status='Under Treatment' WHERE patient_id=%s", (appt['patient_id'],))

    # Notify patient
    if appt.get('patient_user_id'):
        message = (
            f"Visit details updated by Dr. {appt['doctor_name']}.\n"
            f"Treatment: {treatment}\n"
            f"BP: {bp}, Weight: {weight}\n"
            f"Next Visit: {next_visit_date} {next_visit_time}\n"
            f"Reports Needed: {reports_text}\n"
            f"Prescription: {prescription}"
        )
        db.execute("""
            INSERT INTO notifications (user_id, message, type, related_appointment_id)
            VALUES (%s, %s, %s, %s)
        """, (appt['patient_user_id'], message, "visit_update", appointment_id))
        db.execute("""
            INSERT INTO notifications (user_id, message, type, related_appointment_id)
            VALUES (%s, %s, %s, %s)
        """, (
            appt['patient_user_id'],
            f"Your next visit is scheduled on {next_visit_date} at {next_visit_time} with Dr. {appt['doctor_name']}.",
            "reminder",
            appointment_id
        ))

    flash("Visit saved. Appointment moved to next visit date and patient notified.", "success")
    return _redirect_back_to_filtered_appointments()


@doctor_bp.route('/appointments/<int:appointment_id>/complete', methods=['POST'])
@require_role('doctor')
def complete_appointment(appointment_id):
    doctor_id = session.get('doctor_id')
    final_prescription = request.form.get('final_prescription', '').strip()
    confirm_complete = request.form.get('confirm_complete')

    if confirm_complete != 'yes':
        flash("Please confirm treatment completion to proceed.", "danger")
        return _redirect_back_to_filtered_appointments()

    if not final_prescription:
        flash("Final prescription is required to complete appointment.", "danger")
        return _redirect_back_to_filtered_appointments()

    # Fetch appointment and patient info
    appt_data = db.fetch_one("""
        SELECT a.appointment_id, a.patient_id, a.next_visit_date, a.appointment_date, p.user_id AS patient_user_id, d.name AS doctor_name
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s AND a.doctor_id=%s
    """, (appointment_id, doctor_id))

    if not appt_data:
        flash("Appointment not found.", "danger")
        return _redirect_back_to_filtered_appointments()

    future_block = db.fetch_one("""
        SELECT 1 AS blocked
        FROM appointments
        WHERE appointment_id=%s
          AND doctor_id=%s
          AND DATE(COALESCE(next_visit_date, appointment_date)) > CURDATE()
        LIMIT 1
    """, (appointment_id, doctor_id))
    if future_block:
        flash("Cannot complete this appointment before its scheduled visit date.", "danger")
        return _redirect_back_to_filtered_appointments()

    updated = db.execute("""
        UPDATE appointments
        SET status='Completed', prescription=%s, slot_active=NULL
        WHERE appointment_id=%s AND doctor_id=%s
    """, (final_prescription, appointment_id, doctor_id))

    if updated:
        # Update patient status to "Treated"
        db.execute("UPDATE patients SET status='Treated' WHERE patient_id=%s", (appt_data['patient_id'],))

        # Notify patient that appointment completed
        if appt_data.get('patient_user_id'):
            message = "Your treatment has been marked completed. Final prescription has been shared in your appointment records."
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt_data['patient_user_id'], message, "appointment", appointment_id))
            
            # Notify about next visit if scheduled
            if appt_data.get('next_visit_date'):
                next_visit_msg = f"Your next visit with Dr. {appt_data['doctor_name']} is scheduled for {appt_data['next_visit_date']}."
                db.execute("""
                    INSERT INTO notifications (user_id, message, type, related_appointment_id)
                    VALUES (%s, %s, %s, %s)
                """, (appt_data['patient_user_id'], next_visit_msg, "reminder", appointment_id))

        # Notify receptionist(s) to proceed with billing
        receptionists = db.fetch_all("SELECT user_id FROM receptionist") or []
        for r in receptionists:
            if r.get('user_id'):
                db.execute("""
                    INSERT INTO notifications (user_id, message, type, related_appointment_id)
                    VALUES (%s, %s, %s, %s)
                """, (r['user_id'], "An appointment was completed. Proceed to billing.", "billing", appointment_id))
        
        flash("Appointment completed successfully!", "success")
    else:
        flash("Unable to complete appointment.", "danger")

    return _redirect_back_to_filtered_appointments()
