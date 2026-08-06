-- Hospital Management System Database Schema
-- MySQL Database Creation Script
-- Create database first, then run this script

USE hospital_db;

-- Users Table (for login credentials)
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin', 'receptionist', 'doctor', 'patient') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Doctors Table
CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    qualification VARCHAR(150),
    specialization VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(15),
    experience_years INT,
    available BOOLEAN DEFAULT TRUE,
    photo_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Patients Table
CREATE TABLE IF NOT EXISTS patients (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL,
    gender ENUM('Male', 'Female', 'Other') NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(15),
    disease VARCHAR(100),
    blood_group VARCHAR(5),
    status VARCHAR(50) DEFAULT 'Pending',
    health_risk_level ENUM('Low', 'Medium', 'High') DEFAULT 'Low',
    assigned_doctor_id INT,
    address TEXT,
    medical_history TEXT,
    current_condition TEXT,
    allergies TEXT,
    emergency_contact_name VARCHAR(100),
    emergency_contact_phone VARCHAR(15),
    photo_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_doctor_id) REFERENCES doctors(doctor_id) ON DELETE SET NULL
);

-- Appointments Table
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    status ENUM('Pending', 'Confirmed', 'Completed', 'Cancelled') DEFAULT 'Pending',
    -- Extra clinical/visit fields used by the application (Health Insights, prescriptions, follow-ups)
    treatment TEXT,
    bp VARCHAR(50),
    weight VARCHAR(50),
    prescription TEXT,
    next_visit_date DATE,
    -- Slot locking field used to prevent duplicate active bookings for the same doctor/date/time
    slot_active TINYINT NULL DEFAULT 1,
    reason_for_visit VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE
);

-- Visits Table
CREATE TABLE IF NOT EXISTS visits (
    visit_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    doctor_id INT NOT NULL,
    visit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    progress_notes TEXT NOT NULL,
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id) ON DELETE CASCADE
);

-- Bills Table
CREATE TABLE IF NOT EXISTS bills (
    bill_id INT AUTO_INCREMENT PRIMARY KEY,
    appointment_id INT NOT NULL,
    patient_id INT NOT NULL,
    consultation_fee DECIMAL(10, 2) DEFAULT 500.00,
    treatment_cost DECIMAL(10, 2) DEFAULT 0.00,
    medicines_cost DECIMAL(10, 2) DEFAULT 0.00,
    total_amount DECIMAL(10, 2),
    paid BOOLEAN DEFAULT FALSE,
    payment_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
);

-- Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50),
    is_read BOOLEAN DEFAULT FALSE,
    related_appointment_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (related_appointment_id) REFERENCES appointments(appointment_id) ON DELETE CASCADE
);

-- Feedback Table
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(120),
    rating INT NOT NULL,
    feedback_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Receptionist Table (only one receptionist)
CREATE TABLE IF NOT EXISTS receptionist (
    receptionist_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(15),
    department VARCHAR(100) DEFAULT 'Administration',
    photo_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Admins Table (optional admin profile; admin login is stored in users)
CREATE TABLE IF NOT EXISTS admins (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL DEFAULT 'Admin',
    email VARCHAR(120),
    phone VARCHAR(15),
    photo_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX idx_user_role ON users(role);
CREATE INDEX idx_patient_doctor ON patients(assigned_doctor_id);
CREATE INDEX idx_appointment_status ON appointments(status);
CREATE INDEX idx_appointment_date ON appointments(appointment_date);
-- Unique active booking per doctor slot (allows multiple NULL slot_active rows)
CREATE UNIQUE INDEX uniq_active_doctor_slot ON appointments (doctor_id, appointment_date, appointment_time, slot_active);
CREATE INDEX idx_notification_user ON notifications(user_id);
CREATE INDEX idx_notification_read ON notifications(is_read);
CREATE INDEX idx_feedback_created ON feedback(created_at);


INSERT INTO users (username, password, role) VALUES 
('admin', 'scrypt:32768:8:1$ZQWdHcAOr6ZSlv9k$828f06b31c47d0f161766bd4900713273d79a1b7a8cd2c623f10233fe392500a37a27c8579bfa71434eecb140e6a9238905b16a908f91ee4106535aefeedb67a', 'admin');

-- Insert admin profile if it doesn't exist (links to the admin user above)
INSERT INTO admins (user_id, name, email, phone)
SELECT u.user_id, 'Admin', NULL, NULL
FROM users u
WHERE u.username = 'admin'
  AND NOT EXISTS (SELECT 1 FROM admins a WHERE a.user_id = u.user_id)
LIMIT 1;

-- Insert Fixed Admin Credentials (Password: admin123)
-- Password hash: scrypt (werkzeug)

-- Note: Doctors, Receptionist, and Patients will be added through the application UI
-- For testing, you can manually insert test data or use the registration/setup features

-- Insert 4 Predefined Doctors (without passwords initially - set via UI)
-- These will get their user_id from the users table
-- SQL to add doctors after creating users:
-- INSERT INTO doctors (user_id, name, specialization, department) VALUES
-- (2, 'Dr. Rajesh Kumar', 'Cardiology', 'Cardiac Surgery'),
-- (3, 'Dr. Priya Sharma', 'Orthopedics', 'Orthopedic Surgery'),
-- (4, 'Dr. Amit Patel', 'Dermatology', 'Dermatology'),
-- (5, 'Dr. Neha Gupta', 'General Medicine', 'Internal Medicine');

COMMIT;
