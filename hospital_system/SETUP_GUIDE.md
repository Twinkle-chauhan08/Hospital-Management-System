# Hospital Management System - Setup Instructions

## 🎯 Step-by-Step Setup Guide

### Step 1: Install Python & MySQL

#### Windows
1. **Python**: Download from [python.org](https://www.python.org/downloads/) (3.8+)
   - During installation, check "Add Python to PATH"

2. **MySQL**: Download from [mysql.com](https://dev.mysql.com/downloads/mysql/)
   - Choose MySQL Community Server
   - Default port: 3306
   - Create root password during setup

#### macOS
```bash
# Using Homebrew
brew install python3
brew install mysql
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip mysql-server
```

### Step 2: Navigate to Project Directory

```bash
cd path/to/hospital_system
```

### Step 3: Create Virtual Environment (Optional but Recommended)

#### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

#### macOS/Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Install Required Packages

```bash
pip install -r requirements.txt
```

**Expected packages**:
- Flask==3.0.0
- mysql-connector-python==8.2.0
- python-dotenv==1.0.0
- Werkzeug==3.0.0

### Step 5: Setup MySQL Database

#### Option A: Using Command Line

**Windows (Command Prompt)**:
```bash
mysql -u root -p < database_schema.sql
```
When prompted, enter your MySQL root password.

**macOS/Linux**:
```bash
mysql -u root -p < database_schema.sql
```

#### Option B: Using MySQL Workbench

1. Open MySQL Workbench
2. Connect to your MySQL server
3. File → Open SQL Script → Select `database_schema.sql`
4. Click Execute (⚡ icon) or press Ctrl+Shift+Enter

#### Option C: Manual SQL Execution

1. Open MySQL Command Line or Workbench
2. Copy entire contents of `database_schema.sql`
3. Paste and execute

**What gets created**:
- Database: `hospital_db`
- 7 tables with relationships
- Indexes for performance
- Admin account (credentials below)

### Step 6: Configure Database Connection

**Edit `config.py`**:

```python
class DevelopmentConfig:
    DB_HOST = 'localhost'
    DB_USER = 'root'
    DB_PASSWORD = 'your_mysql_password'  # ← UPDATE THIS
    DB_NAME = 'hospital_db'
    DEBUG = True
    SECRET_KEY = 'hospital-secret-key-2024'
```

**Save the file** after updating password.

### Step 7: Run the Application

```bash
python app.py
```

**Expected output**:
```
==================================================
Hospital Management System
==================================================
 * Running on http://127.0.0.1:5000
 * Debug mode: on
 * Restarting with reloader
```

### Step 8: Access the System

Open your browser and go to:
```
http://localhost:5000
```

You should see the login page.

## 🔐 Default Credentials

### Admin Account
- **Username**: admin
- **Password**: admin123

### Receptionist Account
- **Username**: receptionist
- **Password**: rec123

### Doctor Account (4 available)
- **Username**: doctor1
- **Password**: doc123
- **Also**: doctor2, doctor3, doctor4 (same password)

### Patient Account
- **Register** at `/register` page
- Create new patient account
- System auto-assigns doctor based on disease

## ✅ Verification Checklist

After setup, verify everything works:

- [ ] Flask server starts without errors
- [ ] Can access http://localhost:5000
- [ ] Login with admin credentials works
- [ ] Can view admin dashboard
- [ ] Can register a new patient
- [ ] Can login as patient
- [ ] Can book an appointment
- [ ] Receptionist can confirm appointments
- [ ] Doctor can view patients
- [ ] Bills are generated after appointments

## 🐛 Common Issues & Solutions

### Issue: "Can't connect to MySQL server"
```
Error: Failed to connect to MySQL
```
**Solutions**:
1. Verify MySQL is running
   - Windows: Check Services (mysql80)
   - macOS: `brew services list`
   - Linux: `sudo systemctl status mysql`

2. Check credentials in `config.py`
   - Username should be `root`
   - Password must match your setup
   - Host should be `localhost`

3. Verify database exists:
   ```bash
   mysql -u root -p -e "SHOW DATABASES;"
   ```
   Should show `hospital_db`

### Issue: "ModuleNotFoundError: No module named 'flask'"
```
Error: No module named 'flask'
```
**Solution**:
```bash
pip install -r requirements.txt
```

### Issue: "Port 5000 already in use"
```
Error: Address already in use (':5000')
```
**Solutions**:

Option 1: Kill process using port 5000
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# macOS/Linux
lsof -ti:5000 | xargs kill -9
```

Option 2: Change port in `app.py`
```python
if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5001)  # Change 5000 to 5001
```

### Issue: "Access Denied for user 'root'@'localhost'"
**Solution**:
1. Verify MySQL root password
2. Reset MySQL root password if forgotten
3. Update `config.py` with correct password

### Issue: Database tables not created
**Solution**:
```bash
# Run the schema script
mysql -u root -p hospital_db < database_schema.sql

# Or verify tables exist
mysql -u root -p hospital_db -e "SHOW TABLES;"
```

### Issue: "TemplateNotFound" error
**Solution**:
- Ensure `templates/` folder exists with all HTML files
- Check file names match exactly (case-sensitive on Linux/macOS)

## 📱 Testing the System

### Test Patient Registration Flow
1. Go to http://localhost:5000/register
2. Fill in details:
   - Name: John Doe
   - Age: 35
   - Gender: Male
   - Disease: Heart Disease
   - Email: john@example.com
   - Username: john_patient
   - Password: password123
3. Click "Create Account"
4. Login with new credentials

### Test Appointment Booking
1. Login as patient
2. Click "Book Appointment"
3. Select Doctor: Dr. Rajesh (Cardiologist)
4. Select Date: Tomorrow
5. Select Time: 10:00 AM
6. Add Reason: Regular checkup
7. Click "Book Appointment"

### Test Appointment Confirmation
1. Logout and login as receptionist (receptionist/rec123)
2. Go to "Appointments"
3. Find pending appointment
4. Click "Confirm"
5. Appointment status changes to "Confirmed"

### Test Doctor View
1. Logout and login as doctor (doctor1/doc123)
2. Go to "Patients" - should see newly registered patient
3. Go to "Appointments" - should see confirmed appointment
4. Click "Complete" to mark appointment as done
5. Bill is automatically generated

## 🔄 Workflow Overview

```
Patient Registration
    ↓
Patient Login
    ↓
Book Appointment (Select Doctor, Date, Time)
    ↓
Receptionist Confirms Appointment
    ↓
Doctor Sees Notification
    ↓
Doctor Completes Appointment
    ↓
Bill Generated Automatically
    ↓
Patient Can View Health History
```

## 📊 Accessing Different Dashboards

| Role | URL | Credentials |
|------|-----|-------------|
| Admin | http://localhost:5000/admin/dashboard | admin / admin123 |
| Receptionist | http://localhost:5000/receptionist/dashboard | receptionist / rec123 |
| Doctor | http://localhost:5000/doctor/dashboard | doctor1 / doc123 |
| Patient | http://localhost:5000/patient/dashboard | (registered user) |

## 🎓 Learning Resources

### Understanding the Code

1. **app.py** - Main application logic
   - Routes for each user role
   - Appointment workflow
   - Authentication

2. **database.py** - Database operations
   - Query execution
   - Password hashing
   - Smart features (doctor matching, risk calculation)

3. **config.py** - Configuration
   - Database connection settings
   - Flask configuration

4. **templates/** - HTML pages
   - Login/Register
   - Dashboards for each role
   - Appointment management

5. **static/css/style.css** - Styling
   - Custom theme
   - Bootstrap integration
   - Responsive design

6. **static/js/script.js** - Client-side logic
   - Form validation
   - Notifications
   - Utility functions

## 🚀 Deploying to Production

### Before Deploying
1. Change SECRET_KEY in config.py
2. Set DEBUG = False
3. Use strong database password
4. Configure email for notifications

### Using Gunicorn (Recommended)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Using Docker
Create `Dockerfile`:
```dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

Build and run:
```bash
docker build -t hospital-system .
docker run -p 5000:5000 hospital-system
```

## 💡 Tips & Tricks

1. **Quick Patient Registration**
   - Use predefined diseases from dropdown
   - System auto-assigns best doctor
   - Health risk calculated automatically

2. **View All Appointments**
   - Admin can see hospital-wide appointments
   - Receptionist sees pending confirmations
   - Doctor sees assigned patients

3. **Generate Reports**
   - Admin dashboard shows statistics
   - View disease distribution
   - Monitor doctor workload

4. **Patient Health Insights**
   - View health risk level
   - See assigned doctor
   - Track appointment history

## 📞 Support & Contact

If you encounter issues:
1. Check browser console (F12)
2. Review Flask console output
3. Check MySQL error logs
4. Verify all files are created correctly

---

**Congratulations! Your Hospital Management System is ready! 🏥**
