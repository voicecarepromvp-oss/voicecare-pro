# add_test_voicemails.py
from run import app
from database import db, Voicemail, Clinic

with app.app_context():

    # 1️⃣ Create test clinic
    clinic = Clinic.query.first()
    if not clinic:
        clinic = Clinic(name="Test Clinic")
        db.session.add(clinic)
        db.session.commit()
        print("Created Test Clinic ✅")

    # 2️⃣ Test voicemails
    cases = [
        {"transcript": "I want to schedule a routine appointment."},  # non_urgent
        {"transcript": "I need a medication refill today."},           # urgent
        {"transcript": "I feel like hurting myself."}                 # crisis
    ]

    # 3️⃣ Add voicemails with dummy filename
    for i, c in enumerate(cases, start=1):
        v = Voicemail(
            clinic_id=clinic.id,
            transcript=c["transcript"],
            status="received",
            filename=f"test_audio_{i}.mp3",  # dummy filename
            audio_url=None,
            audio_duration=None,
            source="test"
        )
        db.session.add(v)

    db.session.commit()
    print("Added 3 test voicemails ✅")