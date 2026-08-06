import os
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from werkzeug.utils import secure_filename
from database import db
from routes.auth_routes import require_role
from decimal import Decimal, InvalidOperation

receptionist_bp = Blueprint('receptionist', __name__, url_prefix='/receptionist')
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def _ensure_receptionist_profile_columns():
    col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'receptionist'
          AND column_name = 'photo_path'
        LIMIT 1
    """)
    if not col:
        db.execute("ALTER TABLE receptionist ADD COLUMN photo_path VARCHAR(255) NULL")


def _is_allowed_profile_image(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def _save_receptionist_profile_photo(file_obj, receptionist_id):
    if not file_obj or not file_obj.filename:
        return None
    if not _is_allowed_profile_image(file_obj.filename):
        return "INVALID_FILE_TYPE"

    clean_name = secure_filename(file_obj.filename)
    extension = clean_name.rsplit('.', 1)[1].lower()
    unique_name = f"receptionist_{receptionist_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'receptionist_profiles')
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, unique_name)
    file_obj.save(full_path)
    return f"uploads/receptionist_profiles/{unique_name}"

# Dashboard
@receptionist_bp.route('/dashboard')
@require_role('receptionist')
def receptionist_dashboard():
    _ensure_receptionist_profile_columns()
    pending = (db.fetch_one("SELECT COUNT(*) AS c FROM appointments WHERE status='Pending'") or {"c": 0})['c']
    today = (db.fetch_one("SELECT COUNT(*) AS c FROM appointments WHERE DATE(appointment_date)=CURDATE()") or {"c": 0})['c']
    today_appointments = db.fetch_all("""
        SELECT a.appointment_id, p.name AS patient_name, d.name AS doctor_name,
               a.appointment_date, a.appointment_time, a.status, a.reason_for_visit
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE DATE(a.appointment_date)=CURDATE()
        ORDER BY a.appointment_time ASC
    """) or []
    pending_appointments = db.fetch_all("""
        SELECT a.appointment_id, p.name AS patient_name, d.name AS doctor_name,
               a.appointment_date, a.appointment_time, a.status, a.reason_for_visit
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.status='Pending'
        ORDER BY a.appointment_date ASC, a.appointment_time ASC
    """) or []
    recent_patients = db.fetch_all("""
        SELECT p.patient_id, p.name, p.age, p.gender, p.disease, d.name AS doctor_name
        FROM patients p
        LEFT JOIN doctors d ON p.assigned_doctor_id = d.doctor_id
        ORDER BY p.patient_id DESC
        LIMIT 10
    """) or []
    return render_template(
        'receptionist_dashboard.html',
        pending_count=pending,
        today_count=today,
        today_appointments=today_appointments,
        pending_appointments=pending_appointments,
        recent_patients=recent_patients
    )


@receptionist_bp.route('/profile', methods=['GET', 'POST'])
@require_role('receptionist')
def receptionist_profile():
    _ensure_receptionist_profile_columns()

    uid = session.get('user_id')
    if not uid:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('auth.login'))

    receptionist = db.fetch_one("""
        SELECT r.receptionist_id, r.user_id, r.name, r.email, r.phone, r.photo_path, u.username
        FROM receptionist r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.user_id=%s
    """, (uid,))

    if not receptionist:
        flash("Receptionist profile not found.", "danger")
        return redirect(url_for('receptionist.receptionist_dashboard'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for('receptionist.receptionist_profile'))

        photo_file = request.files.get('profile_photo')
        photo_path = None
        if photo_file and photo_file.filename:
            photo_path = _save_receptionist_profile_photo(photo_file, receptionist['receptionist_id'])
            if photo_path == "INVALID_FILE_TYPE":
                flash("Please upload only PNG, JPG, JPEG, or WEBP image files.", "danger")
                return redirect(url_for('receptionist.receptionist_profile'))

        if photo_path:
            db.execute("""
                UPDATE receptionist
                SET name=%s, email=%s, phone=%s, photo_path=%s
                WHERE receptionist_id=%s
            """, (name, email, phone, photo_path, receptionist['receptionist_id']))
            flash("Profile photo uploaded successfully.", "success")
        else:
            db.execute("""
                UPDATE receptionist
                SET name=%s, email=%s, phone=%s
                WHERE receptionist_id=%s
            """, (name, email, phone, receptionist['receptionist_id']))

        flash("Profile updated successfully.", "success")
        return redirect(url_for('receptionist.receptionist_profile'))

    return render_template('receptionist_profile.html', receptionist=receptionist)

# View all appointments
@receptionist_bp.route('/appointments')
@require_role('receptionist')
def view_appointments():
    search_query = (request.args.get('q') or '').strip()

    sql = """
        SELECT a.*, p.name AS patient_name, d.name AS doctor_name, b.bill_id, b.paid AS bill_paid, a.next_visit_date
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        LEFT JOIN bills b ON a.appointment_id = b.appointment_id
    """
    params = []
    if search_query:
        sql += " WHERE p.name LIKE %s "
        params.append(f"%{search_query}%")
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time DESC "

    appointments = db.fetch_all(sql, tuple(params))
    return render_template('receptionist_appointments.html', appointments=appointments, search_query=search_query)

# Confirm appointment
@receptionist_bp.route('/confirm-appointment/<int:appointment_id>', methods=['POST'])
@require_role('receptionist')
def confirm_appointment(appointment_id):
    db.execute("UPDATE appointments SET status='Confirmed', slot_active=1 WHERE appointment_id=%s", (appointment_id,))
    appt = db.fetch_one("""
        SELECT a.appointment_id, a.appointment_date, a.appointment_time,
               p.user_id AS patient_user_id, d.user_id AS doctor_user_id
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s
    """, (appointment_id,))
    if appt:
        # Notify patient
        if appt.get('patient_user_id'):
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['patient_user_id'], "Your appointment has been confirmed.", "appointment", appointment_id))
        # Notify doctor
        if appt.get('doctor_user_id'):
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['doctor_user_id'], "An appointment has been confirmed for you.", "appointment", appointment_id))
    return redirect(url_for('receptionist.view_appointments'))

# Cancel appointment
@receptionist_bp.route('/cancel-appointment/<int:appointment_id>', methods=['POST'])
@require_role('receptionist')
def cancel_appointment(appointment_id):
    db.execute("UPDATE appointments SET status='Cancelled', slot_active=NULL WHERE appointment_id=%s", (appointment_id,))
    
    appt = db.fetch_one("""
        SELECT a.appointment_id, p.user_id AS patient_user_id, d.user_id AS doctor_user_id
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s
    """, (appointment_id,))
    
    if appt:
        # Notify patient
        if appt.get('patient_user_id'):
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['patient_user_id'], "Your appointment has been cancelled by the receptionist.", "cancellation", appointment_id))
        # Notify doctor
        if appt.get('doctor_user_id'):
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (appt['doctor_user_id'], "An appointment has been cancelled.", "cancellation", appointment_id))
            
    flash("Appointment cancelled successfully.", "success")
    return redirect(url_for('receptionist.view_appointments'))

# View bills
@receptionist_bp.route('/bills')
@require_role('receptionist')
def view_bills():
    search_query = (request.args.get('q') or '').strip()

    sql = """
        SELECT b.bill_id, b.appointment_id, p.name AS patient_name, a.appointment_date,
               b.consultation_fee, b.treatment_cost, b.medicines_cost,
               (b.consultation_fee + b.treatment_cost + b.medicines_cost) AS total_amount,
               b.paid
        FROM bills b
        JOIN appointments a ON b.appointment_id = a.appointment_id
        JOIN patients p ON a.patient_id = p.patient_id
    """
    params = []
    if search_query:
        sql += " WHERE p.name LIKE %s "
        params.append(f"%{search_query}%")
    sql += " ORDER BY b.bill_id DESC "

    bills = db.fetch_all(sql, tuple(params))
    return render_template('receptionist_bills.html', bills=bills, search_query=search_query)


@receptionist_bp.route('/generate-bill/<int:appointment_id>', methods=['GET', 'POST'])
@require_role('receptionist')
def generate_bill(appointment_id):
    appointment = db.fetch_one("""
        SELECT a.appointment_id, a.patient_id, a.appointment_date, a.appointment_time, a.status,
               p.name AS patient_name, d.name AS doctor_name, a.next_visit_date
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        WHERE a.appointment_id=%s
    """, (appointment_id,))

    if not appointment:
        flash("Appointment not found.", "danger")
        return redirect(url_for('receptionist.view_appointments'))

    if appointment['status'] not in ('Confirmed', 'Completed'):
        flash("Bills can be generated only for confirmed or completed appointments.", "warning")
        return redirect(url_for('receptionist.view_appointments'))

    existing_bill = db.fetch_one("""
        SELECT bill_id, consultation_fee, treatment_cost, medicines_cost, paid
        FROM bills
        WHERE appointment_id=%s
    """, (appointment_id,))

    # Prevent open/editing for already paid bills.
    if existing_bill and existing_bill['paid']:
        flash("Paid bills cannot be modified.", "warning")
        return redirect(url_for('receptionist.view_bills'))

    if request.method == 'POST':
        # Block updates if the bill is already marked as paid
        if existing_bill and existing_bill['paid']:
            flash("Paid bills cannot be modified.", "warning")
            return redirect(url_for('receptionist.view_bills'))

        try:
            input_consultation_fee = Decimal(request.form.get('consultation_fee', '0') or '0')
            input_treatment_cost = Decimal(request.form.get('treatment_cost', '0') or '0')
            input_medicines_cost = Decimal(request.form.get('medicines_cost', '0') or '0')
        except InvalidOperation:
            flash("Enter valid numeric values for bill amounts.", "danger")
            return render_template(
                'receptionist_generate_bill.html',
                appointment=appointment,
                existing_bill=existing_bill
            )

        if input_consultation_fee < 0 or input_treatment_cost < 0 or input_medicines_cost < 0:
            flash("Bill amounts cannot be negative.", "danger")
            return render_template(
                'receptionist_generate_bill.html',
                appointment=appointment,
                existing_bill=existing_bill
            )

        paid = 1 if request.form.get('paid') == 'on' else 0
        total_amount = input_consultation_fee + input_treatment_cost + input_medicines_cost

        if existing_bill:
            # Update existing unpaid bill or unpaid completed appointment bill.
            updated = db.execute("""
                UPDATE bills
                SET consultation_fee=%s,
                    treatment_cost=%s,
                    medicines_cost=%s,
                    total_amount=%s,
                    paid=%s,
                    payment_date=CASE WHEN %s=1 THEN NOW() ELSE NULL END
                WHERE appointment_id=%s
            """, (
                float(input_consultation_fee), float(input_treatment_cost), float(input_medicines_cost),
                float(total_amount), paid, paid, appointment_id
            ))
            if updated:
                flash("Bill updated successfully.", "success")
            else:
                flash("Failed to update bill. Please try again.", "danger")
        else:
            # Create new bill for this appointment
            inserted = db.execute("""
                INSERT INTO bills
                (appointment_id, patient_id, consultation_fee, treatment_cost, medicines_cost, total_amount, paid, payment_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CASE WHEN %s=1 THEN NOW() ELSE NULL END)
            """, (
                appointment_id, appointment['patient_id'], float(input_consultation_fee), float(input_treatment_cost),
                float(input_medicines_cost), float(total_amount), paid, paid
            ))
            if inserted:
                flash("Bill generated successfully.", "success")
            else:
                flash("Failed to generate bill. Please try again.", "danger")

        # Notify patient about bill
        pat = db.fetch_one("SELECT user_id FROM patients WHERE patient_id=%s", (appointment['patient_id'],)) or {}
        if pat.get('user_id'):
            bill_action = "updated" if existing_bill else "generated"
            payment_state = "Paid" if paid else "Unpaid"
            db.execute("""
                INSERT INTO notifications (user_id, message, type, related_appointment_id)
                VALUES (%s, %s, %s, %s)
            """, (
                pat['user_id'],
                f"Your bill has been {bill_action}. Total: Rs {float(total_amount):.2f}. Status: {payment_state}.",
                "billing",
                appointment_id
            ))

        return redirect(url_for('receptionist.view_bills'))

    return render_template(
        'receptionist_generate_bill.html',
        appointment=appointment,
        existing_bill=existing_bill
    )
