from run import app
from database import db, User, Clinic

with app.app_context():

    # 1. Create default clinic (if not exists)
    clinic = Clinic.query.filter_by(name="VoiceCare Demo Clinic").first()

    if not clinic:
        clinic = Clinic(
            name="VoiceCare Demo Clinic",
            email="clinic@voicecare.ai",
            ingest_email_token="demo-token-123"
        )
        db.session.add(clinic)
        db.session.commit()
        print("✅ Clinic created")

    # 2. Create admin user (if not exists)
    admin = User.query.filter_by(email="admin@voicecare.ai").first()

    if not admin:
        admin = User(
            email="admin@voicecare.ai",
            role="admin",
            is_admin=True,
            clinic_id=clinic.id
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created")
        print("Email: admin@voicecare.ai")
        print("Password: admin123")
    else:
        print("⚠️ Admin already exists")
