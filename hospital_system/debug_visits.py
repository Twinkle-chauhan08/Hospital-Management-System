from database import db

def check_visit_data():
    print("Checking 'visits' table content...")
    visits = db.fetch_all("SELECT * FROM visits LIMIT 5")
    for v in visits:
        print(v)
    
    print("\nChecking 'appointments' table content...")
    appts = db.fetch_all("SELECT * FROM appointments LIMIT 5")
    for a in appts:
        print(a)

if __name__ == "__main__":
    check_visit_data()
