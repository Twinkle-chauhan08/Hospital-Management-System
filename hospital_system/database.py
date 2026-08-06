"""
Database utility functions for Hospital Management System
Handles MySQL connection and queries
"""

import mysql.connector
from mysql.connector import Error
from config import DevelopmentConfig as Config
import re

class Database:
    """Database connection and operations class for MySQL"""

    def __init__(self):
        self.config = {
            'host': Config.DB_HOST,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD,
            'database': Config.DB_NAME,
            'raise_on_warnings': True
        }

    def get_connection(self):
        """Establish MySQL connection"""
        try:
            conn = mysql.connector.connect(**self.config)
            return conn
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
            return None

    def execute_query(self, query, params=None):
        """Execute INSERT, UPDATE, DELETE queries"""
        conn = self.get_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            rowcount = cursor.rowcount
            cursor.close()
            conn.close()
            return rowcount
        except Error as e:
            print(f"Query error: {e}")
            if conn:
                conn.close()
            return None

    def execute(self, query, params=None):
        """Alias for execute_query"""
        return self.execute_query(query, params)

    def fetch_all(self, query, params=None):
        """Fetch multiple rows"""
        conn = self.get_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return rows
        except Error as e:
            print(f"Fetch all error: {e}")
            if conn:
                conn.close()
            return []

    def fetch_one(self, query, params=None):
        """Fetch a single row"""
        conn = self.get_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            return row
        except Error as e:
            print(f"Fetch one error: {e}")
            if conn:
                conn.close()
            return None

# ==============================
# SMART FEATURES
# ==============================

def validate_password(password):
    """
    Validate password criteria:
    - At least 8 characters long
    - Contains at least one number
    - Contains at least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one numeric character."
        
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character (e.g., @, #, $, etc.)."
        
    return True, ""

def get_disease_to_doctor_mapping():
    return {
        'heart disease': 'Cardiology',
        'cardiac': 'Cardiology',
        'chest pain': 'Cardiology',
        'hypertension': 'Cardiology',
        'bone fracture': 'Orthopedics',
        'arthritis': 'Orthopedics',
        'joint pain': 'Orthopedics',
        'back pain': 'Orthopedics',
        'skin rash': 'Dermatology',
        'acne': 'Dermatology',
        'eczema': 'Dermatology',
        'psoriasis': 'Dermatology',
        'fever': 'General Medicine',
        'flu': 'General Medicine',
        'cold': 'General Medicine',
        'diabetes': 'General Medicine',
        'thyroid': 'General Medicine',
    }

def get_health_risk_level(disease, age):
    high_risk = ['cancer', 'heart disease', 'cardiac', 'diabetes type 2']
    medium_risk = ['hypertension', 'arthritis', 'asthma']

    disease_lower = disease.lower()

    for d in high_risk:
        if d in disease_lower:
            return "High"

    for d in medium_risk:
        if d in disease_lower:
            return "Medium"

    if age > 60:
        return "Medium"

    return "Low"

def get_doctor_recommendation(disease, db):
    mapping = get_disease_to_doctor_mapping()
    specialization = mapping.get(disease.lower(), 'General Medicine')

    query = """
        SELECT doctor_id, name, specialization, department
        FROM doctors
        WHERE specialization = %s AND available = TRUE
        LIMIT 1
    """
    return db.fetch_one(query, (specialization,))

def get_advanced_health_insights(patient_id):
    def _parse_float(value):
        if value is None:
            return None
        text = str(value).strip().lower().replace('kg', '').strip()
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    def _parse_bp(bp_text):
        if not bp_text or '/' not in str(bp_text):
            return None, None
        parts = str(bp_text).split('/')
        if len(parts) != 2:
            return None, None
        try:
            return int(parts[0].strip()), int(parts[1].strip())
        except (TypeError, ValueError):
            return None, None

    patient = db.fetch_one("SELECT * FROM patients WHERE patient_id = %s", (patient_id,))
    if not patient:
        return None

    history = db.fetch_all("""
        SELECT appointment_date, appointment_time, status, bp, weight, treatment, prescription
        FROM appointments
        WHERE patient_id = %s
          AND (
                status = 'Completed'
                OR (
                    status IN ('Confirmed', 'Pending')
                    AND (
                        bp IS NOT NULL
                        OR weight IS NOT NULL
                        OR treatment IS NOT NULL
                        OR prescription IS NOT NULL
                    )
                )
          )
        ORDER BY appointment_date ASC, appointment_time ASC
    """, (patient_id,)) or []

    disease = (patient.get('disease') or '').strip().lower()
    age = int(patient.get('age') or 0)

    insights = {
        'risk_level': patient.get('health_risk_level', 'Low') or 'Low',
        'risk_percentage': 25,
        'vitals_trend': [],
        'summary': "Collecting enough records to build a stronger health assessment.",
        'recommendations': [],
        'prediction': "Awaiting Clinical Data",
        'history_data': history
    }

    risk_score = 10

    # Age contribution
    if age >= 70:
        risk_score += 30
        insights['vitals_trend'].append("Age group is senior, so closer follow-up is recommended.")
    elif age >= 55:
        risk_score += 20
        insights['vitals_trend'].append("Age-related screening should be done regularly.")
    elif age >= 40:
        risk_score += 12
    elif age > 0:
        risk_score += 5

    # Disease contribution
    condition_tag = "general"
    if any(k in disease for k in ['heart', 'cardiac', 'hypertension', 'bp']):
        risk_score += 28
        condition_tag = "cardiac"
    elif any(k in disease for k in ['diabetes', 'sugar']):
        risk_score += 25
        condition_tag = "diabetes"
    elif any(k in disease for k in ['asthma', 'copd', 'lung']):
        risk_score += 18
        condition_tag = "respiratory"
    elif any(k in disease for k in ['kidney', 'renal', 'liver', 'cancer', 'stroke']):
        risk_score += 30
        condition_tag = "critical"
    elif disease:
        risk_score += 10

    # Vitals analysis from history
    weights = []
    systolic_values = []
    diastolic_values = []

    for row in history:
        weight = _parse_float(row.get('weight'))
        if weight is not None:
            weights.append(weight)
        s, d = _parse_bp(row.get('bp'))
        if s is not None and d is not None:
            systolic_values.append(s)
            diastolic_values.append(d)

    if len(weights) >= 2:
        delta = weights[-1] - weights[0]
        if abs(delta) >= 2:
            direction = "increasing" if delta > 0 else "decreasing"
            insights['vitals_trend'].append(f"Weight trend is {direction} by {abs(delta):.1f} kg across visits.")
            if delta > 0:
                risk_score += 8
    elif len(weights) == 1:
        insights['vitals_trend'].append(f"Current recorded weight: {weights[0]:.1f} kg.")

    latest_sys = systolic_values[-1] if systolic_values else None
    latest_dia = diastolic_values[-1] if diastolic_values else None

    if latest_sys is not None and latest_dia is not None:
        insights['vitals_trend'].append(f"Latest BP is {latest_sys}/{latest_dia} mmHg.")
        if latest_sys >= 160 or latest_dia >= 100:
            risk_score += 30
            insights['vitals_trend'].append("BP is in high range and needs prompt monitoring.")
        elif latest_sys >= 140 or latest_dia >= 90:
            risk_score += 20
            insights['vitals_trend'].append("BP is above normal range.")
        elif latest_sys >= 130 or latest_dia >= 85:
            risk_score += 10
            insights['vitals_trend'].append("BP is borderline elevated.")
    else:
        insights['vitals_trend'].append("Blood pressure trend needs more recorded visits.")

    # Risk level mapping
    risk_score = max(5, min(95, risk_score))
    insights['risk_percentage'] = risk_score
    if risk_score >= 70:
        insights['risk_level'] = "High"
    elif risk_score >= 40:
        insights['risk_level'] = "Medium"
    else:
        insights['risk_level'] = "Low"

    # Prediction label
    if not history:
        insights['prediction'] = "Baseline Monitoring"
    elif insights['risk_level'] == 'High':
        insights['prediction'] = "Needs Close Follow-up"
    elif len(history) >= 3 and latest_sys is not None and latest_sys < 130:
        insights['prediction'] = "Improving"
    else:
        insights['prediction'] = "Stable with Monitoring"

    # Recommendations by condition + risk
    recs = []
    if condition_tag == "cardiac":
        recs.extend([
            "Limit salt intake and avoid processed foods.",
            "Track blood pressure twice daily and share with your doctor.",
            "Maintain 30 minutes of light activity unless advised otherwise."
        ])
    elif condition_tag == "diabetes":
        recs.extend([
            "Follow controlled carbohydrate meals and fixed meal timings.",
            "Check blood sugar regularly and keep a daily log.",
            "Do regular foot and eye screening as advised."
        ])
    elif condition_tag == "respiratory":
        recs.extend([
            "Avoid dust, smoke, and pollution triggers.",
            "Use inhalers/medicines exactly as prescribed.",
            "Seek review early if breathlessness increases."
        ])
    elif condition_tag == "critical":
        recs.extend([
            "Do strict follow-up with specialist as scheduled.",
            "Never skip prescribed medicines.",
            "Report warning symptoms immediately."
        ])
    else:
        recs.extend([
            "Continue regular health checkups every 3-6 months.",
            "Maintain balanced diet, hydration, and sleep routine.",
            "Keep follow-up records updated after each visit."
        ])

    if age >= 60:
        recs.append("Schedule periodic kidney, heart, and vision screening due to age risk.")
    if insights['risk_level'] == 'High':
        recs.append("Plan early follow-up appointment within 1-2 weeks.")
    elif insights['risk_level'] == 'Medium':
        recs.append("Follow-up in 2-4 weeks to monitor trend.")
    else:
        recs.append("Continue preventive care and routine annual screening.")

    # Remove duplicates while preserving order
    insights['recommendations'] = list(dict.fromkeys(recs))

    insights['summary'] = (
        f"Based on age ({age if age else 'N/A'}), condition "
        f"('{patient.get('disease') or 'General Checkup'}'), and {len(history)} clinical record(s), "
        f"your current risk is assessed as {insights['risk_level']} ({insights['risk_percentage']}%). "
        f"Status: {insights['prediction']}."
    )

    return insights

# Initialize global database instance
db = Database()
