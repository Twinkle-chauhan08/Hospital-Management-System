from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from database import db, validate_password
from werkzeug.security import generate_password_hash, check_password_hash
from config import DevelopmentConfig as Config
from functools import wraps
from email.message import EmailMessage
import hashlib
import hmac
import os
import random
import smtplib
import time
import re
from datetime import timedelta

# ================================
# Blueprint
# ================================
auth_bp = Blueprint('auth', __name__)
OTP_EXPIRY_SECONDS = 300
MAX_OTP_ATTEMPTS = 5

# ================================
# Helper Functions
# ================================
def is_logged_in():
    return 'user_id' in session


def get_user_role():
    return session.get('role')


def _normalize_email(value):
    return (value or '').strip().lower()


def _hash_otp(email, otp):
    raw = f"{email}|{otp}|{Config.SECRET_KEY}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _send_login_otp(email, otp):
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    sender = os.environ.get('SMTP_FROM', smtp_user or 'no-reply@hospital.local')

    subject = "Your Medicare Hospital Login OTP"
    body = f"Your OTP is {otp}. It will expire in {OTP_EXPIRY_SECONDS // 60} minutes."

    # Developer fallback when SMTP is not configured.
    if not (smtp_host and smtp_user and smtp_password):
        return True, f"Demo OTP: {otp}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(body)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        return True, "OTP sent to your email."
    except Exception as exc:
        print(f"OTP email send failed: {exc}")
        return False, "Could not send OTP right now. Please try again."


def _find_active_user_by_email(email):
    matches = db.fetch_all("""
        SELECT u.user_id, u.username, u.role, p.patient_id AS role_id, p.email AS matched_email
        FROM users u
        JOIN patients p ON p.user_id = u.user_id
        WHERE u.is_active = 1 AND LOWER(p.email) = %s

        UNION ALL

        SELECT u.user_id, u.username, u.role, d.doctor_id AS role_id, d.email AS matched_email
        FROM users u
        JOIN doctors d ON d.user_id = u.user_id
        WHERE u.is_active = 1 AND LOWER(d.email) = %s

        UNION ALL

        SELECT u.user_id, u.username, u.role, r.receptionist_id AS role_id, r.email AS matched_email
        FROM users u
        JOIN receptionist r ON r.user_id = u.user_id
        WHERE u.is_active = 1 AND LOWER(r.email) = %s
    """, (email, email, email)) or []

    if not matches:
        return None, "No active account found with this verified email."

    if len(matches) > 1:
        return None, "Multiple accounts found with this email. Please contact admin."

    return matches[0], None


def _redirect_for_role(role):
    if role == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    if role == 'doctor':
        return redirect(url_for('doctor.doctor_dashboard'))
    if role == 'receptionist':
        return redirect(url_for('receptionist.receptionist_dashboard'))
    if role == 'patient':
        return redirect(url_for('patient.patient_dashboard'))
    return redirect(url_for('main.home'))


def _set_authenticated_session(user):
    session.clear()
    session['user_id'] = user['user_id']
    session['username'] = user['username']
    role = (user.get('role') or '').strip().lower()
    session['role'] = role

    if role == 'patient':
        patient_id = user.get('role_id')
        if not patient_id:
            patient = db.fetch_one(
                "SELECT patient_id FROM patients WHERE user_id=%s",
                (user['user_id'],)
            )
            patient_id = patient['patient_id'] if patient else None
        if patient_id:
            session['patient_id'] = patient_id

    if role == 'doctor':
        doctor_id = user.get('role_id')
        if not doctor_id:
            doctor = db.fetch_one(
                "SELECT doctor_id FROM doctors WHERE user_id=%s",
                (user['user_id'],)
            )
            doctor_id = doctor['doctor_id'] if doctor else None
        if doctor_id:
            session['doctor_id'] = doctor_id


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please login first.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def require_role(role):
    """
    Restrict access to specific role
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):

            if not is_logged_in():
                return redirect(url_for('auth.login'))

            if session.get('role') != role:
                return "Unauthorized Access", 403

            return f(*args, **kwargs)
        return wrapper
    return decorator


# ================================
# Index Route
# ================================
@auth_bp.route('/portal')
def index():
    if not is_logged_in():
        return redirect(url_for('main.home'))

    role = get_user_role()

    # Dynamically redirect to correct dashboard
    try:
        return redirect(url_for(f"{role}.{role}_dashboard"))
    except:
        return redirect(url_for('main.home'))


# ================================
# Login Route
# ================================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'password_login':
            session.pop('pending_login', None)
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password')
            remember_me = request.form.get('remember_me') == 'on'

            if not username or not password:
                return render_template('login.html', error="Username and password are required.")

            user = db.fetch_one(
                "SELECT * FROM users WHERE username=%s AND is_active=1",
                (username,)
            )

            if not user or not check_password_hash(user.get('password', ''), password):
                return render_template('login.html', error="Invalid username or password.")

            _set_authenticated_session(user)
            session.permanent = remember_me
            if remember_me:
                # Keep user logged in for 30 days when "Remember me" is checked.
                session.permanent_session_lifetime = timedelta(days=30)

            role = (session.get('role') or '').lower()
            if role == 'patient' and 'patient_id' not in session:
                session.clear()
                return render_template('login.html', error="Patient record not found. Please contact support.")

            flash("Login successful!", "success")
            return _redirect_for_role(role)

        if action == 'send_otp':
            session.pop('pending_login', None)
            auth_method = (request.form.get('auth_method') or '').strip().lower()
            if auth_method != 'google':
                return render_template('login.html', error="OTP login is available only via Google login.")

            email = _normalize_email(request.form.get('email'))

            if not email:
                return render_template('login.html', error="Email is required.")

            user, lookup_error = _find_active_user_by_email(email)
            if lookup_error:
                return render_template('login.html', error=lookup_error)

            otp = f"{random.randint(0, 999999):06d}"
            session['pending_login'] = {
                'user_id': user['user_id'],
                'username': user['username'],
                'role': user['role'],
                'role_id': user['role_id'],
                'email': email,
                'auth_method': 'google',
                'otp_hash': _hash_otp(email, otp),
                'expires_at': int(time.time()) + OTP_EXPIRY_SECONDS,
                'attempts': 0
            }

            sent, message = _send_login_otp(email, otp)
            if not sent:
                session.pop('pending_login', None)
                return render_template('login.html', error=message)

            flash(message, "info")
            return render_template(
                'login.html',
                otp_step=True,
                email=email,
                auth_method='google'
            )

        if action == 'verify_otp':
            pending = session.get('pending_login')
            email = _normalize_email(request.form.get('email') or (pending or {}).get('email'))
            otp = (request.form.get('otp') or '').strip()

            if not pending or pending.get('email') != email:
                session.pop('pending_login', None)
                return render_template('login.html', error="OTP session expired. Please request a new OTP.")

            if (pending.get('auth_method') or '').lower() != 'google':
                session.pop('pending_login', None)
                return render_template('login.html', error="OTP login is available only for Google login.")

            if int(time.time()) > int(pending.get('expires_at', 0)):
                session.pop('pending_login', None)
                return render_template('login.html', error="OTP expired. Please request a new OTP.")

            if not otp.isdigit() or len(otp) != 6:
                return render_template(
                    'login.html',
                    otp_step=True,
                    email=email,
                    auth_method='google',
                    error="Please enter a valid 6-digit OTP."
                )

            if not hmac.compare_digest(_hash_otp(email, otp), pending.get('otp_hash', '')):
                pending['attempts'] = int(pending.get('attempts', 0)) + 1
                session['pending_login'] = pending
                remaining = MAX_OTP_ATTEMPTS - pending['attempts']

                if remaining <= 0:
                    session.pop('pending_login', None)
                    return render_template('login.html', error="Too many invalid OTP attempts. Please try again.")

                return render_template(
                    'login.html',
                    otp_step=True,
                    email=email,
                    auth_method='google',
                    error=f"Invalid OTP. {remaining} attempt(s) left."
                )

            _set_authenticated_session(pending)
            role = (session.get('role') or '').lower()
            if role == 'patient' and 'patient_id' not in session:
                session.clear()
                return render_template('login.html', error="Patient record not found. Please contact support.")

            flash("Login successful!", "success")
            return _redirect_for_role(role)

        return render_template('login.html', error="Invalid login action.")

    return render_template('login.html')


# ================================
# Logout Route
# ================================
@auth_bp.route('/logout')
@require_login
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('auth.login'))


# ================================
# Register Route (Patient Only)
# ================================
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = (request.form.get('name') or '').strip()
        age = request.form.get('age')
        gender = request.form.get('gender')
        email = (request.form.get('email') or '').strip()
        disease = request.form.get('disease')
        blood_group = request.form.get('blood_group')
        phone = (request.form.get('phone') or '').strip()
        address = (request.form.get('address') or '').strip()

        # Validation
        if not all([username, password, confirm_password, name, age, gender, blood_group, phone, address]):
            return render_template('register.html', error="All required fields must be filled")

        if not re.fullmatch(r'[A-Za-z ]+', name):
            return render_template('register.html', error="Full Name must contain only alphabets and spaces.")

        if not str(age).isdigit():
            return render_template('register.html', error="Age must be a valid number.")

        if not email.lower().endswith('@gmail.com'):
            return render_template('register.html', error="Email must be a valid Gmail address (@gmail.com).")

        if not re.fullmatch(r'[0-9]{10}', phone):
            return render_template('register.html', error="Phone number must be exactly 10 digits.")

        if not re.fullmatch(r'[A-Za-z]+', username):
            return render_template('register.html', error="Username must contain only alphabetic characters.")

        if password != confirm_password:
            return render_template('register.html', error="Passwords do not match")

        # Password validation
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            return render_template('register.html', error=error_msg)

        # Check existing user
        existing_user = db.fetch_one(
            "SELECT user_id FROM users WHERE username=%s",
            (username,)
        )

        if existing_user:
            return render_template('register.html', error=f"Error: The username '{username}' is already taken. Please choose a different username.")

        # Hash password
        hashed_password = generate_password_hash(password)

        # Insert user
        result = db.execute_query(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'patient')",
            (username, hashed_password)
        )

        if result is None:
            return render_template('register.html', error="Error creating account. Please try again.")

        # Get created user_id
        user = db.fetch_one(
            "SELECT user_id FROM users WHERE username=%s",
            (username,)
        )

        if not user:
            return render_template('register.html', error="Error retrieving user data.")

        user_id = user['user_id']

        # Insert patient record with 'New' status
        # Initial fields are filled, but doctor will update them later
        result = db.execute_query(
            """
            INSERT INTO patients 
            (user_id, name, age, gender, email, disease, blood_group, phone, address, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'New')
            """,
            (user_id, name, age, gender, email, disease, blood_group, phone, address)
        )

        if result is None:
            # Cleanup user if patient record creation fails
            db.execute_query("DELETE FROM users WHERE user_id=%s", (user_id,))
            return render_template('register.html', error="Error creating patient record. Please try again.")

        flash("Account created successfully! Please login.", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html')


# ================================
# Forgot Password
# ================================
@auth_bp.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        identifier = (request.form.get('identifier') or '').strip()
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not all([identifier, new_password, confirm_password]):
            return render_template('forgot_password.html', error="All fields are required", identifier=identifier)

        if new_password != confirm_password:
            return render_template('forgot_password.html', error="Passwords do not match", identifier=identifier)

        # Password validation
        is_valid, error_msg = validate_password(new_password)
        if not is_valid:
            return render_template('forgot_password.html', error=error_msg, identifier=identifier)

        user = db.fetch_one("SELECT user_id, username FROM users WHERE username=%s AND is_active=1", (identifier,))

        if not user:
            email = _normalize_email(identifier)
            user, lookup_error = _find_active_user_by_email(email)
            if lookup_error:
                return render_template('forgot_password.html', error="User not found or inactive", identifier=identifier)

        if not user:
            return render_template('forgot_password.html', error="User not found or inactive", identifier=identifier)

        hashed = generate_password_hash(new_password)
        db.execute_query("UPDATE users SET password=%s WHERE user_id=%s", (hashed, user['user_id']))

        flash("Password updated successfully. Please login.", "success")
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')
