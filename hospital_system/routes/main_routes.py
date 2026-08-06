from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import db

main_bp = Blueprint('main', __name__)


def ensure_feedback_table():
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


def get_live_home_stats():
    total_patients_row = db.fetch_one("SELECT COUNT(*) AS c FROM patients") or {"c": 0}
    total_doctors_row = db.fetch_one("SELECT COUNT(*) AS c FROM doctors") or {"c": 0}
    total_appointments_row = db.fetch_one("SELECT COUNT(*) AS c FROM appointments") or {"c": 0}
    completed_appointments_row = db.fetch_one(
        "SELECT COUNT(*) AS c FROM appointments WHERE status='Completed'"
    ) or {"c": 0}

    founding_year = 2001
    current_year = datetime.now().year
    years_of_trust = max(1, current_year - founding_year)

    return {
        "patients": int(total_patients_row.get("c", 0) or 0),
        "doctors": int(total_doctors_row.get("c", 0) or 0),
        "appointments": int(total_appointments_row.get("c", 0) or 0),
        "completed_appointments": int(completed_appointments_row.get("c", 0) or 0),
        "years_of_trust": years_of_trust,
    }


def _ensure_home_profile_columns():
    # These columns are added in other blueprints too, but the home page can be hit first.
    doctor_qual_col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'doctors'
          AND column_name = 'qualification'
        LIMIT 1
    """)
    if not doctor_qual_col:
        db.execute("ALTER TABLE doctors ADD COLUMN qualification VARCHAR(150) NULL")

    doctor_photo_col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'doctors'
          AND column_name = 'photo_path'
        LIMIT 1
    """)
    if not doctor_photo_col:
        db.execute("ALTER TABLE doctors ADD COLUMN photo_path VARCHAR(255) NULL")

    receptionist_photo_col = db.fetch_one("""
        SELECT 1 AS c
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'receptionist'
          AND column_name = 'photo_path'
        LIMIT 1
    """)
    if not receptionist_photo_col:
        db.execute("ALTER TABLE receptionist ADD COLUMN photo_path VARCHAR(255) NULL")


def get_live_doctors():
    _ensure_home_profile_columns()
    rows = db.fetch_all("""
        SELECT doctor_id, name, specialization, qualification, experience_years, available, photo_path
        FROM doctors
        ORDER BY available DESC, name ASC
    """) or []

    # Attach a URL for the front-end (home page + live doctors API)
    for r in rows:
        p = (r.get('photo_path') or '').strip()
        r['photo_url'] = url_for('static', filename=p) if p else None
    return rows

@main_bp.route('/')
def home():
    ensure_feedback_table()

    doctors = get_live_doctors()
    stats = get_live_home_stats()

    feedbacks = db.fetch_all("""
        SELECT feedback_id, name, rating, feedback_text, created_at
        FROM feedback
        ORDER BY feedback_id DESC
        LIMIT 6
    """) or []

    user_profile = None
    dashboard_url = None
    profile_url = None
    if session.get('user_id'):
        _ensure_home_profile_columns()
        role = (session.get('role') or '').lower()
        uid = session.get('user_id')
        if role == 'patient':
            user_profile = db.fetch_one("SELECT name, email, phone, photo_path FROM patients WHERE user_id=%s", (uid,))
        elif role == 'doctor':
            user_profile = db.fetch_one("SELECT name, email, phone, specialization, photo_path FROM doctors WHERE user_id=%s", (uid,))
        elif role == 'receptionist':
            user_profile = db.fetch_one("SELECT name, email, phone, photo_path FROM receptionist WHERE user_id=%s", (uid,))
        else:
            user_profile = {"name": session.get('username')}
        user_profile = user_profile or {"name": session.get('username')}
        user_profile['role'] = role
        photo_path = (user_profile.get('photo_path') or '').strip()
        user_profile['photo_url'] = url_for('static', filename=photo_path) if photo_path else None
        try:
            dashboard_url = url_for(f"{role}.{role}_dashboard")
        except Exception:
            dashboard_url = None

        try:
            if role == 'patient':
                profile_url = url_for('patient.patient_profile')
            elif role == 'doctor':
                profile_url = url_for('doctor.doctor_profile')
            elif role == 'receptionist':
                profile_url = url_for('receptionist.receptionist_profile')
            else:
                profile_url = dashboard_url
        except Exception:
            profile_url = dashboard_url
    return render_template(
        'home.html',
        doctors=doctors,
        stats=stats,
        feedbacks=feedbacks,
        user_profile=user_profile,
        dashboard_url=dashboard_url,
        profile_url=profile_url
    )

@main_bp.route('/ui')
def ui_preview():
    return render_template('ui_spa.html')
@main_bp.route('/contact', methods=['POST'])
def contact():
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip()
    message = (request.form.get('message') or '').strip()
    if not all([name, email, message]):
        flash("Please fill all contact form fields.", "warning")
        return redirect(url_for('main.home') + "#contact")
    flash("Thank you for contacting us. We'll get back to you soon.", "success")
    return redirect(url_for('main.home') + "#contact")


@main_bp.route('/api/feedback', methods=['POST'])
def api_feedback():
    ensure_feedback_table()

    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    email = (payload.get('email') or '').strip()
    feedback_text = (payload.get('feedback_text') or '').strip()

    try:
        rating = int(payload.get('rating') or 0)
    except (TypeError, ValueError):
        rating = 0

    if not name or not feedback_text or rating < 1 or rating > 5:
        return jsonify({"success": False, "error": "Please provide name, feedback and a rating between 1 and 5."}), 400

    inserted = db.execute_query("""
        INSERT INTO feedback (name, email, rating, feedback_text)
        VALUES (%s, %s, %s, %s)
    """, (name, email or None, rating, feedback_text))

    if inserted is None:
        return jsonify({"success": False, "error": "Could not save feedback right now."}), 500

    row = db.fetch_one("""
        SELECT feedback_id, name, rating, feedback_text, created_at
        FROM feedback
        ORDER BY feedback_id DESC
        LIMIT 1
    """)

    return jsonify({"success": True, "feedback": row})

@main_bp.route('/api/notifications')
def api_notifications():
    uid = session.get('user_id')
    if not uid:
        return jsonify({"count": 0, "notifications": []})
    rows = db.fetch_all("""
        SELECT notification_id, message, type, is_read, created_at
        FROM notifications
        WHERE user_id=%s AND is_read=0
        ORDER BY created_at DESC
        LIMIT 20
    """, (uid,)) or []
    return jsonify({
        "count": len(rows),
        "notifications": rows
    })


@main_bp.route('/api/live-stats')
def api_live_stats():
    return jsonify({"success": True, "stats": get_live_home_stats()})


@main_bp.route('/api/live-doctors')
def api_live_doctors():
    return jsonify({"success": True, "doctors": get_live_doctors()})

@main_bp.route('/api/mark-notification-read/<int:notification_id>', methods=['POST'])
def api_mark_notification_read(notification_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    db.execute_query("UPDATE notifications SET is_read=1 WHERE notification_id=%s AND user_id=%s", (notification_id, uid))
    return jsonify({"success": True})
