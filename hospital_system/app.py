from flask import Flask
from config import DevelopmentConfig as Config
from datetime import datetime, date

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)


def format_date_dmy(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime):
        return value.strftime('%d-%m-%y')
    if isinstance(value, date):
        return value.strftime('%d-%m-%y')
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).strftime('%d-%m-%y')
        except ValueError:
            continue
    return text


def format_datetime_dmy(value):
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime):
        return value.strftime('%d-%m-%y %H:%M')
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).strftime('%d-%m-%y 00:00')
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%d-%m-%y %H:%M')
        except ValueError:
            continue
    return text


def format_month_name(value):
    if not value or not isinstance(value, int) or value < 1 or value > 12:
        return ""
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    return months[value - 1]


app.jinja_env.filters['dmy'] = format_date_dmy
app.jinja_env.filters['dmydt'] = format_datetime_dmy
app.jinja_env.filters['month_name'] = format_month_name

# Register Blueprints
from routes.auth_routes import auth_bp
from routes.admin_routes import admin_bp
from routes.receptionist_routes import receptionist_bp
from routes.doctor_routes import doctor_bp
from routes.patient_routes import patient_bp
from routes.main_routes import main_bp
6
app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(receptionist_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(patient_bp, url_prefix='/patient')

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    return "Internal server error", 500

if __name__ == '__main__':
    print("="*45)
    print("Hospital Management System Running")
    print("="*45)
    app.run(debug=True)
