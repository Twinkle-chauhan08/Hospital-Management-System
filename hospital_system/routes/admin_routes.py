# ==============================
# ADMIN ROUTES
# ==============================

from flask import Blueprint, render_template, Response, request, redirect, url_for, flash
from database import db, validate_password
from routes.auth_routes import require_role
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import csv
import io
from datetime import date
import os
import re

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

admin_bp = Blueprint('admin', __name__)
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def _ensure_admin_profile_table():
    # Create admins profile table if missing (optional profile for admin role)
    db.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL DEFAULT 'Admin',
            email VARCHAR(120),
            phone VARCHAR(15),
            photo_path VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)


def _is_allowed_profile_image(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_IMAGE_EXTENSIONS


def _save_admin_profile_photo(file_obj, user_id):
    if not file_obj or not file_obj.filename:
        return None
    if not _is_allowed_profile_image(file_obj.filename):
        return "INVALID_FILE_TYPE"

    clean_name = secure_filename(file_obj.filename)
    extension = clean_name.rsplit('.', 1)[1].lower()
    unique_name = f"admin_{user_id}_{date.today().strftime('%Y%m%d')}.{extension}"

    # Save into the real app static folder, regardless of the current working directory.
    from flask import current_app

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'admin_profiles')
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, unique_name)
    file_obj.save(full_path)
    return f"uploads/admin_profiles/{unique_name}"


def _is_alpha_text(value, allow_spaces=True, allow_commas=False):
    if value is None:
        return False
    if allow_commas:
        pattern = r'^[A-Za-z]+(?:[\s,-][A-Za-z]+)*$'
    else:
        pattern = r'^[A-Za-z]+(?:[\s-][A-Za-z]+)*$' if allow_spaces else r'^[A-Za-z]+$'
    return bool(re.fullmatch(pattern, value.strip()))


def _is_valid_username(value, allow_underscore=True):
    if value is None:
        return False
    # Allows letters and optionally one underscore if allowed
    if allow_underscore:
        return bool(re.fullmatch(r'^[A-Za-z]+(?:_[A-Za-z]+)?$', value.strip()))
    else:
        return bool(re.fullmatch(r'^[A-Za-z]+$', value.strip()))


def _is_valid_phone(value):
    if value is None or value.strip() == '':
        return False
    return bool(re.fullmatch(r'^[0-9]{10}$', value.strip()))


def _is_valid_medicare_email(value):
    if value is None or value.strip() == '':
        return False
    return bool(re.fullmatch(r'^[A-Za-z0-9._%+-]+@medicare\.com$', value.strip()))


def _csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _pdf_table_response(filename, title, headers, rows, subtitle=None):
    if not REPORTLAB_AVAILABLE:
        flash("PDF export dependency missing. Install reportlab first.", "warning")
        return redirect(url_for('admin.admin_reports'))

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(36, y, title)
    y -= 18
    pdf.setFont("Helvetica", 10)
    if subtitle:
        pdf.drawString(36, y, subtitle)
        y -= 16

    col_count = max(1, len(headers))
    col_width = (width - 72) / col_count

    def draw_header_row():
        nonlocal y
        pdf.setFont("Helvetica-Bold", 9)
        for idx, head in enumerate(headers):
            pdf.drawString(36 + idx * col_width, y, str(head)[:24])
        y -= 14
        pdf.line(36, y, width - 36, y)
        y -= 10

    draw_header_row()
    pdf.setFont("Helvetica", 9)

    if not rows:
        pdf.drawString(36, y, "No records found.")
        y -= 14
    else:
        for row in rows:
            if y < 60:
                pdf.showPage()
                y = height - 40
                draw_header_row()
                pdf.setFont("Helvetica", 9)
            for idx, value in enumerate(row):
                pdf.drawString(36 + idx * col_width, y, str(value)[:24])
            y -= 12

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _get_appointment_register_rows(date_from=None, date_to=None, doctor_id=None, status=None):
    filters = []
    params = []
    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)
    if doctor_id:
        filters.append("a.doctor_id = %s")
        params.append(doctor_id)
    if status:
        filters.append("a.status = %s")
        params.append(status)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    return db.fetch_all(f"""
        SELECT a.appointment_id,
               p.name AS patient_name,
               d.name AS doctor_name,
               a.appointment_date,
               a.appointment_time,
               a.status,
               a.reason_for_visit
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        {where_clause}
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, tuple(params)) or []


def _get_doctor_performance_rows(date_from=None, date_to=None):
    filters = []
    params = []
    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    return db.fetch_all(f"""
        SELECT d.name AS doctor_name,
               COUNT(a.appointment_id) AS total_appointments,
               SUM(CASE WHEN a.status='Confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN a.status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN a.status='Cancelled' THEN 1 ELSE 0 END) AS cancelled
        FROM doctors d
        LEFT JOIN appointments a ON d.doctor_id = a.doctor_id
        {where_clause}
        GROUP BY d.doctor_id, d.name
        ORDER BY d.name
    """, tuple(params)) or []


def _get_appointment_status_trend_rows(granularity='day', date_from=None, date_to=None):
    granularity = (granularity or 'day').lower()
    if granularity not in ('day', 'month'):
        granularity = 'day'
    period_expr = "DATE_FORMAT(appointment_date, '%%Y-%%m')" if granularity == 'month' else "DATE(appointment_date)"
    filters = []
    params = []
    if date_from:
        filters.append("appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("appointment_date <= %s")
        params.append(date_to)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = db.fetch_all(f"""
        SELECT {period_expr} AS period,
               SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancelled,
               COUNT(*) AS total
        FROM appointments
        {where_clause}
        GROUP BY period
        ORDER BY period
    """, tuple(params)) or []
    return granularity, rows


def _get_billing_collection_summary(date_from=None, date_to=None):
    filters = []
    params = []
    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    return db.fetch_one(f"""
        SELECT COUNT(b.bill_id) AS total_bills,
               COALESCE(SUM(b.total_amount), 0) AS total_billed,
               COALESCE(SUM(CASE WHEN b.paid=1 THEN b.total_amount ELSE 0 END), 0) AS paid_amount,
               COALESCE(SUM(CASE WHEN b.paid=0 THEN b.total_amount ELSE 0 END), 0) AS unpaid_amount,
               SUM(CASE WHEN b.paid=1 THEN 1 ELSE 0 END) AS paid_bills,
               SUM(CASE WHEN b.paid=0 THEN 1 ELSE 0 END) AS unpaid_bills
        FROM bills b
        JOIN appointments a ON b.appointment_id = a.appointment_id
        {where_clause}
    """, tuple(params)) or {}


def _get_daily_summary_data(report_date):
    if report_date:
        date_expr = "%s"
        date_params = (report_date,)
    else:
        date_expr = "CURDATE()"
        date_params = ()

    appointment_stats = db.fetch_one(f"""
        SELECT COUNT(*) AS total_appointments,
               SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancelled,
               COUNT(DISTINCT patient_id) AS total_patients_today
        FROM appointments
        WHERE appointment_date = {date_expr}
    """, date_params) or {}

    doctors_available = db.fetch_one(
        "SELECT COUNT(*) AS c FROM doctors WHERE available=TRUE"
    ) or {"c": 0}

    billing_stats = db.fetch_one(f"""
        SELECT COUNT(b.bill_id) AS bills_generated,
               COALESCE(SUM(b.total_amount), 0) AS revenue_today,
               COALESCE(SUM(CASE WHEN b.paid=1 THEN b.total_amount ELSE 0 END), 0) AS paid_today,
               COALESCE(SUM(CASE WHEN b.paid=0 THEN b.total_amount ELSE 0 END), 0) AS unpaid_today
        FROM bills b
        JOIN appointments a ON b.appointment_id = a.appointment_id
        WHERE a.appointment_date = {date_expr}
    """, date_params) or {}

    selected_date = report_date or str(date.today())
    summary = {
        "selected_date": selected_date,
        "total_appointments": appointment_stats.get('total_appointments', 0) or 0,
        "total_patients_today": appointment_stats.get('total_patients_today', 0) or 0,
        "doctors_available": doctors_available.get('c', 0) or 0,
        "pending": appointment_stats.get('pending', 0) or 0,
        "confirmed": appointment_stats.get('confirmed', 0) or 0,
        "completed": appointment_stats.get('completed', 0) or 0,
        "cancelled": appointment_stats.get('cancelled', 0) or 0,
        "bills_generated": billing_stats.get('bills_generated', 0) or 0,
        "revenue_today": float(billing_stats.get('revenue_today', 0) or 0),
        "paid_today": float(billing_stats.get('paid_today', 0) or 0),
        "unpaid_today": float(billing_stats.get('unpaid_today', 0) or 0),
    }
    return summary


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


# ==============================
# ADMIN DASHBOARD
# ==============================
@admin_bp.route('/dashboard')
@require_role('admin')
def admin_dashboard():

    # ---- Total Counts ----
    total_patients_row = db.fetch_one("SELECT COUNT(*) AS c FROM patients")
    total_doctors_row = db.fetch_one("SELECT COUNT(*) AS c FROM doctors")

    total_patients = total_patients_row['c'] if total_patients_row else 0
    total_doctors = total_doctors_row['c'] if total_doctors_row else 0

    # ---- Appointments ----
    appointments = db.fetch_all("""
        SELECT a.*, 
               p.name AS patient_name, 
               d.name AS doctor_name
        FROM appointments a
        LEFT JOIN patients p ON a.patient_id = p.patient_id
        LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
        ORDER BY a.appointment_date DESC,
                 a.appointment_time DESC
    """)

    # ---- Doctors & Their Patients ----
    doctors_rows = db.fetch_all(
        "SELECT doctor_id, name, specialization FROM doctors"
    )

    doctors = {}

    for d in doctors_rows:
        docs_patients = db.fetch_all(
            "SELECT patient_id FROM patients WHERE assigned_doctor_id=%s",
            (d['doctor_id'],)
        )

        doctors[d['doctor_id']] = {
            "name": d["name"],
            "specialization": d["specialization"],
            "patients": docs_patients
        }

    status_rows = db.fetch_all("""
        SELECT status, COUNT(*) AS c
        FROM appointments
        GROUP BY status
        ORDER BY status
    """) or []
    appointment_status_labels = [r['status'] for r in status_rows]
    appointment_status_counts = [r['c'] for r in status_rows]

    billing_summary = db.fetch_one("""
        SELECT
            COUNT(b.bill_id) AS total_bills,
            COALESCE(SUM(b.total_amount), 0) AS total_billed,
            COALESCE(SUM(CASE WHEN b.paid=1 THEN b.total_amount ELSE 0 END), 0) AS paid_amount,
            COALESCE(SUM(CASE WHEN b.paid=0 THEN b.total_amount ELSE 0 END), 0) AS unpaid_amount,
            SUM(CASE WHEN b.paid=1 THEN 1 ELSE 0 END) AS paid_bills,
            SUM(CASE WHEN b.paid=0 THEN 1 ELSE 0 END) AS unpaid_bills
        FROM bills b
    """) or {}

    dept_rows = db.fetch_all("""
        SELECT d.department AS dept, COUNT(*) AS c
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.doctor_id
        GROUP BY d.department
        ORDER BY c DESC
    """) or []
    department_labels = [r['dept'] for r in dept_rows]
    department_counts = [r['c'] for r in dept_rows]

    monthly_appt_rows = db.fetch_all("""
        SELECT DATE_FORMAT(a.appointment_date, '%Y-%m') AS ym,
               DATE_FORMAT(a.appointment_date, '%b %Y') AS label,
               COUNT(*) AS c
        FROM appointments a
        GROUP BY ym, label
        ORDER BY ym
    """) or []
    monthly_appt_labels = [r['label'] for r in monthly_appt_rows]
    monthly_appt_counts = [r['c'] for r in monthly_appt_rows]

    monthly_rev_rows = db.fetch_all("""
        SELECT DATE_FORMAT(b.payment_date, '%Y-%m') AS ym,
               DATE_FORMAT(b.payment_date, '%b %Y') AS label,
               COALESCE(SUM(b.total_amount), 0) AS amt
        FROM bills b
        WHERE b.paid=1 AND b.payment_date IS NOT NULL
        GROUP BY ym, label
        ORDER BY ym
    """) or []
    monthly_rev_labels = [r['label'] for r in monthly_rev_rows]
    monthly_rev_amounts = [float(r['amt']) for r in monthly_rev_rows]

    top_doctor_rows = db.fetch_all("""
        SELECT d.name AS name, COUNT(p.patient_id) AS c
        FROM doctors d
        LEFT JOIN patients p ON p.assigned_doctor_id = d.doctor_id
        GROUP BY d.doctor_id, d.name
        ORDER BY c DESC
        LIMIT 5
    """) or []
    top_doctor_labels = [f"Dr. {r['name']}" for r in top_doctor_rows]
    top_doctor_counts = [r['c'] for r in top_doctor_rows]

    # Today's appointments count
    todays_row = db.fetch_one("SELECT COUNT(*) AS c FROM appointments WHERE appointment_date = CURDATE()") or {"c": 0}
    todays_appointments = todays_row['c']

    # Recent patient registrations
    recent_patients = db.fetch_all("""
        SELECT p.name, p.age, p.gender, p.disease, d.name AS doctor_name
        FROM patients p
        LEFT JOIN doctors d ON p.assigned_doctor_id = d.doctor_id
        ORDER BY p.patient_id DESC
        LIMIT 10
    """) or []

    return render_template(
        "admin_dashboard.html",
        total_patients=total_patients,
        total_doctors=total_doctors,
        appointments=appointments,
        doctors=doctors,
        appointment_status_labels=appointment_status_labels,
        appointment_status_counts=appointment_status_counts,
        billing_summary=billing_summary,
        department_labels=department_labels,
        department_counts=department_counts,
        monthly_appt_labels=monthly_appt_labels,
        monthly_appt_counts=monthly_appt_counts,
        monthly_rev_labels=monthly_rev_labels,
        monthly_rev_amounts=monthly_rev_amounts,
        top_doctor_labels=top_doctor_labels,
        top_doctor_counts=top_doctor_counts,
        todays_appointments=todays_appointments,
        recent_patients=recent_patients
    )


@admin_bp.route('/profile', methods=['GET', 'POST'])
@require_role('admin')
def admin_profile():
    _ensure_admin_profile_table()

    from flask import session, request

    uid = session.get('user_id')
    if not uid:
        flash("Session expired. Please login again.", "danger")
        return redirect(url_for('auth.login'))

    # Ensure an admin profile row exists for this admin user.
    existing = db.fetch_one("SELECT admin_id FROM admins WHERE user_id=%s", (uid,))
    if not existing:
        db.execute(
            "INSERT INTO admins (user_id, name) VALUES (%s, %s)",
            (uid, session.get('username') or 'Admin'),
        )

    admin = db.fetch_one("""
        SELECT a.admin_id, a.user_id, a.name, a.email, a.phone, a.photo_path, u.username
        FROM admins a
        JOIN users u ON a.user_id = u.user_id
        WHERE a.user_id=%s
    """, (uid,))

    if not admin:
        flash("Admin profile not found.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for('admin.admin_profile'))

        photo_file = request.files.get('profile_photo')
        photo_path = None
        if photo_file and photo_file.filename:
            photo_path = _save_admin_profile_photo(photo_file, uid)
            if photo_path == "INVALID_FILE_TYPE":
                flash("Please upload only PNG, JPG, JPEG, or WEBP image files.", "danger")
                return redirect(url_for('admin.admin_profile'))

        if photo_path:
            db.execute("""
                UPDATE admins
                SET name=%s, email=%s, phone=%s, photo_path=%s
                WHERE user_id=%s
            """, (name, email, phone, photo_path, uid))
            flash("Profile photo uploaded successfully.", "success")
        else:
            db.execute("""
                UPDATE admins
                SET name=%s, email=%s, phone=%s
                WHERE user_id=%s
            """, (name, email, phone, uid))

        flash("Admin profile updated successfully.", "success")
        return redirect(url_for('admin.admin_profile'))

    return render_template("admin_profile.html", admin=admin)


# ==============================
# VIEW ALL PATIENTS
# ==============================
@admin_bp.route('/patients')
@require_role('admin')
def admin_view_patients():

    patients = db.fetch_all("""
        SELECT p.*,
               d.name AS doctor_name
        FROM patients p
        LEFT JOIN doctors d
               ON p.assigned_doctor_id = d.doctor_id
        ORDER BY p.patient_id DESC
    """)

    return render_template(
        "admin_patients.html",
        patients=patients
    )


# ==============================
# VIEW FEEDBACK
# ==============================
@admin_bp.route('/feedback')
@require_role('admin')
def admin_feedback():
    # Feedback table can be created from the home page, but admin may open this first.
    db.execute_query("""
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(120),
            rating INT NOT NULL,
            feedback_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    search_query = (request.args.get('q') or '').strip()

    sql = """
        SELECT feedback_id, name, email, rating, feedback_text, created_at
        FROM feedback
    """
    params = []
    if search_query:
        sql += " WHERE name LIKE %s OR email LIKE %s OR feedback_text LIKE %s "
        like = f"%{search_query}%"
        params.extend([like, like, like])

    sql += " ORDER BY feedback_id DESC "

    feedbacks = db.fetch_all(sql, tuple(params)) or []
    return render_template("admin_feedback.html", feedbacks=feedbacks, search_query=search_query)


@admin_bp.route('/doctors', methods=['GET', 'POST'])
@require_role('admin')
def admin_doctors():
    _ensure_doctor_profile_columns()
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        name = (request.form.get('name') or '').strip()
        qualification = (request.form.get('qualification') or '').strip() or None
        specialization = (request.form.get('specialization') or '').strip()
        department = (request.form.get('department') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None
        experience_years = request.form.get('experience_years')
        available = 1 if request.form.get('available') == 'on' else 0

        if name.lower().startswith('dr. '):
            name = name[4:].strip()

        if not all([username, password, name, specialization, qualification, department, experience_years, email, phone]):
            flash("Please fill all doctor fields. All fields are mandatory.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_valid_username(username):
            flash("Doctor username must contain only alphabetic characters and at most one underscore.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_alpha_text(name):
            flash("Doctor name must contain only letters and spaces.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_alpha_text(department):
            flash("Doctor department must contain only letters and spaces.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_alpha_text(specialization):
            flash("Doctor specialization must contain only letters and spaces.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_alpha_text(qualification, allow_commas=True):
            flash("Doctor qualification must contain only letters, spaces, and commas.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not str(experience_years).isdigit():
            flash("Doctor experience must be a numeric value.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_valid_phone(phone):
            flash("Doctor phone number must contain only digits.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        if not _is_valid_medicare_email(email):
            flash("Doctor email must be a valid Medicare email ending with @medicare.com.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        # Password validation
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "danger")
            return redirect(url_for('admin.admin_doctors'))

        existing_user = db.fetch_one("SELECT user_id FROM users WHERE username=%s", (username,))
        if existing_user:
            flash(f"Error: The username '{username}' is already taken. Please choose a different username.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        # Check for duplicate email or phone in doctors table
        existing_doctor = db.fetch_one("SELECT doctor_id FROM doctors WHERE email=%s OR phone=%s", (email, phone))
        if existing_doctor:
            flash("Error: A doctor with this email or phone number is already registered.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        hashed_password = generate_password_hash(password)
        user_created = db.execute(
            "INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, 'doctor', 1)",
            (username, hashed_password)
        )
        if not user_created:
            flash("Could not create doctor login.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        user = db.fetch_one("SELECT user_id FROM users WHERE username=%s", (username,))
        if not user:
            flash("Doctor user record not found after creation.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        doctor_created = db.execute("""
            INSERT INTO doctors
            (user_id, name, qualification, specialization, department, email, phone, experience_years, available)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user['user_id'], name, qualification, specialization, department, email, phone,
            int(experience_years) if experience_years else None, available
        ))

        if not doctor_created:
            db.execute("DELETE FROM users WHERE user_id=%s", (user['user_id'],))
            flash("Could not create doctor profile.", "danger")
            return redirect(url_for('admin.admin_doctors'))

        flash("Doctor added successfully.", "success")
        return redirect(url_for('admin.admin_doctors'))

    doctors = db.fetch_all("""
        SELECT d.doctor_id,
               d.name,
               d.qualification,
               d.specialization,
               d.department,
               d.experience_years,
               d.available,
               d.email,
               d.phone,
               COUNT(p.patient_id) AS patient_count
        FROM doctors d
        LEFT JOIN patients p ON p.assigned_doctor_id = d.doctor_id
        GROUP BY d.doctor_id, d.name, d.qualification, d.specialization, d.department, d.experience_years, d.available, d.email, d.phone
        ORDER BY d.doctor_id DESC
    """) or []

    return render_template("admin_doctors.html", doctors=doctors)


@admin_bp.route('/doctors/<int:doctor_id>/delete', methods=['POST'])
@require_role('admin')
def delete_doctor(doctor_id):
    # Fetch the user_id associated with this doctor to delete from users table as well
    doctor = db.fetch_one("SELECT user_id FROM doctors WHERE doctor_id=%s", (doctor_id,))
    
    if not doctor:
        flash("Doctor not found.", "danger")
        return redirect(url_for('admin.admin_doctors'))

    user_id = doctor['user_id']

    # Delete doctor profile (this might fail if there are foreign key constraints with appointments)
    # Check for appointments first
    appointments = db.fetch_one("SELECT COUNT(*) AS c FROM appointments WHERE doctor_id=%s", (doctor_id,))
    if appointments and appointments['c'] > 0:
        flash(f"Cannot delete doctor. They have {appointments['c']} existing appointments. Cancel or complete them first.", "warning")
        return redirect(url_for('admin.admin_doctors'))

    # Delete from doctors table
    db.execute("DELETE FROM doctors WHERE doctor_id=%s", (doctor_id,))
    
    # Delete from users table (which handles the login)
    db.execute("DELETE FROM users WHERE user_id=%s", (user_id,))

    flash("Doctor and their login account deleted successfully.", "success")
    return redirect(url_for('admin.admin_doctors'))


@admin_bp.route('/appointments')
@require_role('admin')
def admin_appointments():
    appointments = db.fetch_all("""
        SELECT a.appointment_id,
               a.appointment_date,
               a.appointment_time,
               a.status,
               a.reason_for_visit,
               p.name AS patient_name,
               d.name AS doctor_name,
               b.paid AS bill_paid
        FROM appointments a
        LEFT JOIN patients p ON a.patient_id = p.patient_id
        LEFT JOIN doctors d ON a.doctor_id = d.doctor_id
        LEFT JOIN bills b ON a.appointment_id = b.appointment_id
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """) or []

    return render_template("admin_appointments.html", appointments=appointments)


@admin_bp.route('/reports')
@require_role('admin')
def admin_reports():
    doctors = db.fetch_all("SELECT doctor_id, name FROM doctors ORDER BY name") or []
    return render_template("admin_reports.html", doctors=doctors)


@admin_bp.route('/reports/appointment-register')
@require_role('admin')
def report_appointment_register():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    doctor_id = request.args.get('doctor_id')
    status = request.args.get('status')

    filters = []
    params = []

    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)
    if doctor_id:
        filters.append("a.doctor_id = %s")
        params.append(doctor_id)
    if status:
        filters.append("a.status = %s")
        params.append(status)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    rows = db.fetch_all(f"""
        SELECT a.appointment_id,
               p.name AS patient_name,
               d.name AS doctor_name,
               a.appointment_date,
               a.appointment_time,
               a.status,
               a.reason_for_visit
        FROM appointments a
        JOIN patients p ON a.patient_id = p.patient_id
        JOIN doctors d ON a.doctor_id = d.doctor_id
        {where_clause}
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, tuple(params)) or []

    data = [[
        r.get('appointment_id', ''),
        r.get('patient_name', ''),
        r.get('doctor_name', ''),
        r.get('appointment_date', ''),
        r.get('appointment_time', ''),
        r.get('status', ''),
        r.get('reason_for_visit', '')
    ] for r in rows]

    return _csv_response(
        "appointment_register_report.csv",
        ["Appointment ID", "Patient Name", "Doctor Name", "Date", "Time", "Status", "Reason"],
        data
    )


@admin_bp.route('/reports/doctor-performance')
@require_role('admin')
def report_doctor_performance():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    filters = []
    params = []

    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    rows = db.fetch_all(f"""
        SELECT d.name AS doctor_name,
               COUNT(a.appointment_id) AS total_appointments,
               SUM(CASE WHEN a.status='Confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN a.status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN a.status='Cancelled' THEN 1 ELSE 0 END) AS cancelled
        FROM doctors d
        LEFT JOIN appointments a ON d.doctor_id = a.doctor_id
        {where_clause}
        GROUP BY d.doctor_id, d.name
        ORDER BY d.name
    """, tuple(params)) or []

    data = [[
        r.get('doctor_name', ''),
        r.get('total_appointments', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0
    ] for r in rows]

    return _csv_response(
        "doctor_performance_report.csv",
        ["Doctor Name", "Total Appointments", "Confirmed", "Completed", "Cancelled"],
        data
    )


@admin_bp.route('/reports/appointment-register/view')
@require_role('admin')
def report_appointment_register_view():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    doctor_id = request.args.get('doctor_id')
    status = request.args.get('status')
    rows = _get_appointment_register_rows(date_from, date_to, doctor_id, status)
    headers = ["Appointment ID", "Patient Name", "Doctor Name", "Date", "Time", "Status", "Reason"]
    table_rows = [[
        r.get('appointment_id', ''),
        r.get('patient_name', ''),
        r.get('doctor_name', ''),
        r.get('appointment_date', ''),
        r.get('appointment_time', ''),
        r.get('status', ''),
        r.get('reason_for_visit', ''),
    ] for r in rows]
    params = {"date_from": date_from, "date_to": date_to, "doctor_id": doctor_id, "status": status}
    params = {k: v for k, v in params.items() if v}
    return render_template(
        "admin_report_table_view.html",
        report_title="Appointment Register",
        headers=headers,
        rows=table_rows,
        csv_url=url_for('admin.report_appointment_register', **params),
        pdf_url=url_for('admin.report_appointment_register_pdf', **params),
        back_url=url_for('admin.admin_reports')
    )


@admin_bp.route('/reports/appointment-register/pdf')
@require_role('admin')
def report_appointment_register_pdf():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    doctor_id = request.args.get('doctor_id')
    status = request.args.get('status')
    rows = _get_appointment_register_rows(date_from, date_to, doctor_id, status)
    headers = ["Appointment ID", "Patient Name", "Doctor Name", "Date", "Time", "Status", "Reason"]
    data = [[
        r.get('appointment_id', ''),
        r.get('patient_name', ''),
        r.get('doctor_name', ''),
        r.get('appointment_date', ''),
        r.get('appointment_time', ''),
        r.get('status', ''),
        r.get('reason_for_visit', ''),
    ] for r in rows]
    return _pdf_table_response("appointment_register_report.pdf", "Appointment Register Report", headers, data)


@admin_bp.route('/reports/doctor-performance/view')
@require_role('admin')
def report_doctor_performance_view():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rows = _get_doctor_performance_rows(date_from, date_to)
    headers = ["Doctor Name", "Total Appointments", "Confirmed", "Completed", "Cancelled"]
    table_rows = [[
        r.get('doctor_name', ''),
        r.get('total_appointments', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0,
    ] for r in rows]
    params = {"date_from": date_from, "date_to": date_to}
    params = {k: v for k, v in params.items() if v}
    return render_template(
        "admin_report_table_view.html",
        report_title="Doctor Performance",
        headers=headers,
        rows=table_rows,
        csv_url=url_for('admin.report_doctor_performance', **params),
        pdf_url=url_for('admin.report_doctor_performance_pdf', **params),
        back_url=url_for('admin.admin_reports')
    )


@admin_bp.route('/reports/doctor-performance/pdf')
@require_role('admin')
def report_doctor_performance_pdf():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    rows = _get_doctor_performance_rows(date_from, date_to)
    headers = ["Doctor Name", "Total Appointments", "Confirmed", "Completed", "Cancelled"]
    data = [[
        r.get('doctor_name', ''),
        r.get('total_appointments', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0,
    ] for r in rows]
    return _pdf_table_response("doctor_performance_report.pdf", "Doctor Performance Report", headers, data)


# ==============================
# RECEPTIONISTS MANAGEMENT
# ==============================
@admin_bp.route('/receptionists', methods=['GET', 'POST'])
@require_role('admin')
def admin_receptionists():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        department = (request.form.get('department') or '').strip()

        if not all([username, password, name, email, phone, department]):
            flash("Please fill all receptionist fields. All fields are mandatory.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        if not _is_valid_username(username, allow_underscore=False):
            flash("Receptionist username must contain only alphabetic characters (no underscores or spaces).", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        if not _is_alpha_text(name):
            flash("Receptionist name must contain only letters and spaces.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        if not _is_alpha_text(department):
            flash("Receptionist department must contain only letters and spaces.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        if not _is_valid_phone(phone):
            flash("Receptionist phone number must contain only digits.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        if not _is_valid_medicare_email(email):
            flash("Receptionist email must be a valid Medicare email ending with @medicare.com.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        # Password validation
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            flash(error_msg, "danger")
            return redirect(url_for('admin.admin_receptionists'))

        existing_user = db.fetch_one("SELECT user_id FROM users WHERE username=%s", (username,))
        if existing_user:
            flash(f"Error: The username '{username}' is already taken. Please choose a different username.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        # Check for duplicate email or phone in receptionist table
        existing_receptionist = db.fetch_one("SELECT receptionist_id FROM receptionist WHERE email=%s OR phone=%s", (email, phone))
        if existing_receptionist:
            flash("Error: A receptionist with this email or phone number is already registered.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        hashed_password = generate_password_hash(password)
        created = db.execute("INSERT INTO users (username, password, role, is_active) VALUES (%s, %s, 'receptionist', 1)", (username, hashed_password))
        if not created:
            flash("Could not create receptionist login.", "danger")
            return redirect(url_for('admin.admin_receptionists'))

        user = db.fetch_one("SELECT user_id FROM users WHERE username=%s", (username,))
        db.execute("""
            INSERT INTO receptionist (user_id, name, email, phone, department)
            VALUES (%s, %s, %s, %s, %s)
        """, (user['user_id'], name, email, phone, department))

        flash("Receptionist added successfully.", "success")
        return redirect(url_for('admin.admin_receptionists'))

    receptionists = db.fetch_all("""
        SELECT r.receptionist_id, r.name, r.email, r.phone, r.department, u.username
        FROM receptionist r
        JOIN users u ON r.user_id = u.user_id
        ORDER BY r.receptionist_id DESC
    """) or []

    return render_template("admin_receptionists.html", receptionists=receptionists)


@admin_bp.route('/receptionists/delete/<int:receptionist_id>', methods=['POST'])
@require_role('admin')
def admin_delete_receptionist(receptionist_id):
    receptionist = db.fetch_one("SELECT user_id FROM receptionist WHERE receptionist_id = %s", (receptionist_id,))
    if not receptionist:
        flash("Receptionist not found.", "warning")
        return redirect(url_for('admin.admin_receptionists'))

    user_id = receptionist['user_id']

    # Delete from receptionist table first
    db.execute("DELETE FROM receptionist WHERE receptionist_id = %s", (receptionist_id,))
    
    # Delete from users table (which handles the login)
    deleted = db.execute("DELETE FROM users WHERE user_id = %s AND role = 'receptionist'", (user_id,))
    
    if not deleted:
        flash("Could not delete receptionist account.", "danger")
    else:
        flash("Receptionist and their login account removed successfully.", "success")

    return redirect(url_for('admin.admin_receptionists'))


@admin_bp.route('/reports/daily-summary')
@require_role('admin')
def report_daily_summary():
    report_date = request.args.get('date')
    summary = _get_daily_summary_data(report_date)
    date_value = summary["selected_date"]
    data = [[
        date_value,
        summary["total_appointments"],
        summary["total_patients_today"],
        summary["doctors_available"],
        summary["pending"],
        summary["confirmed"],
        summary["completed"],
        summary["cancelled"],
        summary["bills_generated"],
        summary["revenue_today"],
        summary["paid_today"],
        summary["unpaid_today"]
    ]]

    return _csv_response(
        "daily_hospital_summary_report.csv",
        [
            "Date", "Total Appointments", "Total Patients Today", "Doctors Available",
            "Pending", "Confirmed", "Completed", "Cancelled",
            "Bills Generated", "Revenue Today", "Paid Today", "Unpaid Today"
        ],
        data
    )


@admin_bp.route('/reports/daily-summary/view')
@require_role('admin')
def report_daily_summary_view():
    report_date = request.args.get('date')
    summary = _get_daily_summary_data(report_date)
    return render_template("admin_report_daily_summary_view.html", summary=summary)


@admin_bp.route('/reports/daily-summary/pdf')
@require_role('admin')
def report_daily_summary_pdf():
    if not REPORTLAB_AVAILABLE:
        flash("PDF export dependency missing. Install reportlab first.", "warning")
        return redirect(url_for('admin.admin_reports'))

    report_date = request.args.get('date')
    summary = _get_daily_summary_data(report_date)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, y, "Medicare Hospital - Daily Summary Report")
    y -= 24

    pdf.setFont("Helvetica", 11)
    pdf.drawString(40, y, f"Date: {summary['selected_date']}")
    y -= 18

    lines = [
        f"Total Appointments: {summary['total_appointments']}",
        f"Total Patients Today: {summary['total_patients_today']}",
        f"Doctors Available: {summary['doctors_available']}",
        f"Pending: {summary['pending']}",
        f"Confirmed: {summary['confirmed']}",
        f"Completed: {summary['completed']}",
        f"Cancelled: {summary['cancelled']}",
        f"Bills Generated: {summary['bills_generated']}",
        f"Revenue Today: Rs {summary['revenue_today']:.2f}",
        f"Paid Today: Rs {summary['paid_today']:.2f}",
        f"Unpaid Today: Rs {summary['unpaid_today']:.2f}",
    ]

    for line in lines:
        pdf.drawString(40, y, line)
        y -= 18

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"daily_summary_{summary['selected_date']}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@admin_bp.route('/reports/appointment-status-trend')
@require_role('admin')
def report_appointment_status_trend():
    granularity = (request.args.get('granularity') or 'day').lower()
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    if granularity not in ('day', 'month'):
        granularity = 'day'

    period_expr = (
        "DATE_FORMAT(appointment_date, '%%Y-%%m')"
        if granularity == 'month'
        else "DATE(appointment_date)"
    )

    filters = []
    params = []

    if date_from:
        filters.append("appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("appointment_date <= %s")
        params.append(date_to)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    rows = db.fetch_all(f"""
        SELECT {period_expr} AS period,
               SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) AS confirmed,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancelled,
               COUNT(*) AS total
        FROM appointments
        {where_clause}
        GROUP BY period
        ORDER BY period
    """, tuple(params)) or []

    data = [[
        r.get('period', ''),
        r.get('pending', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0,
        r.get('total', 0) or 0
    ] for r in rows]

    return _csv_response(
        "appointment_status_trend_report.csv",
        ["Period", "Pending", "Confirmed", "Completed", "Cancelled", "Total"],
        data
    )


@admin_bp.route('/reports/appointment-status-trend/view')
@require_role('admin')
def report_appointment_status_trend_view():
    granularity = request.args.get('granularity') or 'day'
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    granularity, rows = _get_appointment_status_trend_rows(granularity, date_from, date_to)
    headers = ["Period", "Pending", "Confirmed", "Completed", "Cancelled", "Total"]
    table_rows = [[
        r.get('period', ''),
        r.get('pending', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0,
        r.get('total', 0) or 0,
    ] for r in rows]
    params = {"granularity": granularity, "date_from": date_from, "date_to": date_to}
    params = {k: v for k, v in params.items() if v}
    return render_template(
        "admin_report_table_view.html",
        report_title=f"Appointment Status Trend ({granularity.title()}-wise)",
        headers=headers,
        rows=table_rows,
        csv_url=url_for('admin.report_appointment_status_trend', **params),
        pdf_url=url_for('admin.report_appointment_status_trend_pdf', **params),
        back_url=url_for('admin.admin_reports')
    )


@admin_bp.route('/reports/appointment-status-trend/pdf')
@require_role('admin')
def report_appointment_status_trend_pdf():
    granularity = request.args.get('granularity') or 'day'
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    granularity, rows = _get_appointment_status_trend_rows(granularity, date_from, date_to)
    headers = ["Period", "Pending", "Confirmed", "Completed", "Cancelled", "Total"]
    data = [[
        r.get('period', ''),
        r.get('pending', 0) or 0,
        r.get('confirmed', 0) or 0,
        r.get('completed', 0) or 0,
        r.get('cancelled', 0) or 0,
        r.get('total', 0) or 0,
    ] for r in rows]
    return _pdf_table_response("appointment_status_trend_report.pdf", f"Appointment Status Trend ({granularity.title()}-wise)", headers, data)


@admin_bp.route('/reports/billing-collection')
@require_role('admin')
def report_billing_collection():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    filters = []
    params = []

    if date_from:
        filters.append("a.appointment_date >= %s")
        params.append(date_from)
    if date_to:
        filters.append("a.appointment_date <= %s")
        params.append(date_to)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    summary = db.fetch_one(f"""
        SELECT COUNT(b.bill_id) AS total_bills,
               COALESCE(SUM(b.total_amount), 0) AS total_billed,
               COALESCE(SUM(CASE WHEN b.paid=1 THEN b.total_amount ELSE 0 END), 0) AS paid_amount,
               COALESCE(SUM(CASE WHEN b.paid=0 THEN b.total_amount ELSE 0 END), 0) AS unpaid_amount,
               SUM(CASE WHEN b.paid=1 THEN 1 ELSE 0 END) AS paid_bills,
               SUM(CASE WHEN b.paid=0 THEN 1 ELSE 0 END) AS unpaid_bills
        FROM bills b
        JOIN appointments a ON b.appointment_id = a.appointment_id
        {where_clause}
    """, tuple(params)) or {}

    data = [[
        summary.get('total_bills', 0) or 0,
        summary.get('total_billed', 0) or 0,
        summary.get('paid_amount', 0) or 0,
        summary.get('unpaid_amount', 0) or 0,
        summary.get('paid_bills', 0) or 0,
        summary.get('unpaid_bills', 0) or 0
    ]]

    return _csv_response(
        "billing_collection_report.csv",
        ["Total Bills", "Total Billed", "Paid Amount", "Unpaid Amount", "Paid Bills", "Unpaid Bills"],
        data
    )


@admin_bp.route('/reports/billing-collection/view')
@require_role('admin')
def report_billing_collection_view():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    summary = _get_billing_collection_summary(date_from, date_to)
    headers = ["Total Bills", "Total Billed", "Paid Amount", "Unpaid Amount", "Paid Bills", "Unpaid Bills"]
    table_rows = [[
        summary.get('total_bills', 0) or 0,
        summary.get('total_billed', 0) or 0,
        summary.get('paid_amount', 0) or 0,
        summary.get('unpaid_amount', 0) or 0,
        summary.get('paid_bills', 0) or 0,
        summary.get('unpaid_bills', 0) or 0,
    ]]
    params = {"date_from": date_from, "date_to": date_to}
    params = {k: v for k, v in params.items() if v}
    return render_template(
        "admin_report_table_view.html",
        report_title="Billing Collection",
        headers=headers,
        rows=table_rows,
        csv_url=url_for('admin.report_billing_collection', **params),
        pdf_url=url_for('admin.report_billing_collection_pdf', **params),
        back_url=url_for('admin.admin_reports')
    )


@admin_bp.route('/reports/billing-collection/pdf')
@require_role('admin')
def report_billing_collection_pdf():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    summary = _get_billing_collection_summary(date_from, date_to)
    headers = ["Total Bills", "Total Billed", "Paid Amount", "Unpaid Amount", "Paid Bills", "Unpaid Bills"]
    data = [[
        summary.get('total_bills', 0) or 0,
        summary.get('total_billed', 0) or 0,
        summary.get('paid_amount', 0) or 0,
        summary.get('unpaid_amount', 0) or 0,
        summary.get('paid_bills', 0) or 0,
        summary.get('unpaid_bills', 0) or 0,
    ]]
    return _pdf_table_response("billing_collection_report.pdf", "Billing Collection Report", headers, data)
