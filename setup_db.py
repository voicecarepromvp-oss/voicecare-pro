# setup_db.py
from run import app, db
from database import Clinic
from datetime import datetime, timedelta

print("🔥 Creating tables...")
with app.app_context():
    db.create_all()
print("✅ Tables created.")

print("🔥 Seeding test clinic...")
with app.app_context():
    existing = Clinic.query.filter_by(ingest_email_token="testclinic").first()
    if not existing:
        clinic = Clinic(
            name="Test Clinic",
            email="test@voicecarepro.com",
            ingest_email_token="testclinic",
            plan_name="starter",
            monthly_voicemail_limit=300,
            monthly_voicemail_used=0,
            billing_cycle_start=datetime.utcnow(),
            billing_cycle_end=datetime.utcnow() + timedelta(days=30),
            overage_count=0,
            is_active=True
        )
        db.session.add(clinic)
        db.session.commit()
        print("✅ Test clinic created.")
    else:
        print("⚠️ Test clinic already exists.")

print("🔥 Verifying clinics in DB...")
with app.app_context():
    clinics = Clinic.query.all()
    for c in clinics:
        print(f"Clinic: {c.name}, Token: {c.ingest_email_token}")

print("🎉 Setup complete!")