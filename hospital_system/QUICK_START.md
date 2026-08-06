# Quick Start Checklist

## ✅ Pre-Installation
- [ ] Python 3.8+ installed
- [ ] MySQL Server installed and running
- [ ] Git (optional, for cloning)

## ✅ Installation Steps

### 1. Navigate to Project
```bash
cd d:\PURVA\PI\hospital_system
```
- [ ] Terminal opened in correct directory

### 2. Virtual Environment (Optional)
```bash
python -m venv venv
venv\Scripts\activate
```
- [ ] Virtual environment created (if desired)

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```
- [ ] Flask installed
- [ ] mysql-connector-python installed
- [ ] All packages installed successfully

### 4. Database Setup
```bash
mysql -u root -p < database_schema.sql
```
- [ ] MySQL schema executed
- [ ] Database `hospital_db` created
- [ ] All 7 tables created

### 5. Configure Database
**Edit `config.py`**:
```python
DB_PASSWORD = 'your_actual_password'  # MUST UPDATE!
```
- [ ] Database password updated
- [ ] File saved

### 6. Start Application
```bash
python app.py
```
- [ ] Flask server started
- [ ] Running on http://localhost:5000
- [ ] No errors in console

### 7. Access System
Open browser: http://localhost:5000
- [ ] Login page loads
- [ ] Can see demo credentials info

## ✅ Testing the System

### Login Tests
- [ ] Admin login works (admin / admin123)
- [ ] Receptionist login works (receptionist / rec123)
- [ ] Doctor login works (doctor1 / doc123)

### Patient Registration
- [ ] Register new patient
- [ ] All fields accepted
- [ ] Can login as new patient

### Appointment Workflow
- [ ] Patient can book appointment
- [ ] Receptionist can confirm
- [ ] Doctor can view appointment
- [ ] Appointment marked as completed
- [ ] Bill is generated

### Dashboard Views
- [ ] Admin dashboard shows statistics
- [ ] Receptionist sees pending appointments
- [ ] Doctor can view patient list
- [ ] Patient can view health insights

## ✅ File Structure Verification

Verify all files exist:
```
hospital_system/
├── app.py                    ✅
├── config.py                 ✅
├── database.py               ✅
├── database_schema.sql       ✅
├── requirements.txt          ✅
├── README.md                 ✅
├── SETUP_GUIDE.md            ✅
├── QUICK_START.md            ✅
├── templates/
│   ├── base.html            ✅
│   ├── login.html           ✅
│   ├── register.html        ✅
│   ├── admin_dashboard.html ✅
│   ├── admin_patients.html  ✅
│   ├── admin_doctors.html   ✅
│   ├── admin_appointments.html ✅
│   ├── receptionist_dashboard.html ✅
│   ├── receptionist_appointments.html ✅
│   ├── receptionist_bills.html ✅
│   ├── doctor_dashboard.html ✅
│   ├── doctor_patients.html ✅
│   ├── doctor_appointments.html ✅
│   ├── doctor_patient_details.html ✅
│   ├── patient_dashboard.html ✅
│   ├── patient_book_appointment.html ✅
│   ├── patient_appointments.html ✅
│   ├── patient_health_insights.html ✅
│   ├── error.html           ✅
│   └── access_denied.html   ✅
├── static/
│   ├── css/
│   │   └── style.css        ✅
│   └── js/
│       └── script.js        ✅
```

## 🚀 Quick Commands Reference

### Start Server
```bash
python app.py
```

### Stop Server
```bash
Ctrl + C
```

### Activate Virtual Environment
```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### Check MySQL Status
```bash
mysql -u root -p -e "SELECT 1;"
```

### Reset Database
```bash
mysql -u root -p hospital_db -e "DROP DATABASE hospital_db;"
mysql -u root -p < database_schema.sql
```

## 📝 Important Notes

1. **Database Password**
   - Update in `config.py` with your actual MySQL password
   - Default: 'root' (may not work if you set different password)

2. **Port 5000**
   - Flask runs on port 5000 by default
   - If occupied, change in app.py to 5001

3. **MySQL Running**
   - Ensure MySQL service is running before starting Flask
   - Windows: Check Services (mysql80)

4. **Database Created**
   - `database_schema.sql` must be executed
   - Tables won't exist without running the script

## 🆘 If Something Goes Wrong

### Flask won't start
```bash
# Check Python version
python --version

# Check Flask installation
pip list | grep Flask

# Reinstall if needed
pip install Flask==3.0.0
```

### Can't connect to database
```bash
# Check MySQL is running
mysql -u root -p

# Check credentials in config.py
# Try resetting password if forgotten
```

### Templates not found
```bash
# Verify templates folder exists
dir templates

# Check all HTML files are present
```

### 404 errors
```bash
# Clear browser cache (Ctrl + Shift + Del)
# Restart Flask server
# Check file names match exactly
```

## 📚 Next Steps

1. Read [README.md](README.md) for feature overview
2. Read [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed setup
3. Test all user roles
4. Explore code in app.py
5. Customize as needed

## 🎯 Demo Accounts

### Admin
```
Username: admin
Password: admin123
```

### Receptionist
```
Username: receptionist
Password: rec123
```

### Doctor
```
Username: doctor1, doctor2, doctor3, doctor4
Password: doc123
```

### Patient
```
Register new account at /register
```

## 🎓 Learning Path

1. **Day 1**: Setup & explore login
2. **Day 2**: Register patient & book appointment
3. **Day 3**: Test receptionist workflow
4. **Day 4**: Test doctor functionality
5. **Day 5**: Explore admin dashboard
6. **Day 6+**: Customize and extend

---

**Ready to use your Hospital Management System! 🏥**

For detailed help, see README.md or SETUP_GUIDE.md
