import logging
import time  # ✅ CRITICAL FIX
from run import app  # Needed for Flask app context

# ✅ Updated imports per task
from services.triage_service import extract_triage
from database import db, Voicemail, Clinic, TriageCard

logging.basicConfig(level=logging.INFO)


# ------------------------
# WORKER LOOP
# ------------------------

def worker():
    """Main background worker loop."""
    with app.app_context():
        print("🔥 Worker loop starting with Flask app context...")

        while True:
            try:
                # ✅ Fetch completed voicemails
                voicemails = Voicemail.query.filter_by(status="completed").all()

                print(f"DEBUG: Found {len(voicemails)} completed voicemails")

                processed_count = 0

                for v in voicemails:

                    # ✅ PREVENT REPROCESSING (Task Requirement)
                    existing = TriageCard.query.filter_by(
                        voicemail_id=v.id
                    ).first()

                    if existing:
                        # Already triaged → skip
                        continue

                    # ✅ Skip if no transcript
                    if not v.transcript:
                        logging.warning(
                            f"Voicemail {v.id} has no transcript. Skipping."
                        )
                        continue

                    # ✅ Run triage
                    triage_data = extract_triage(v.transcript)

                    triage = TriageCard(
                        voicemail_id=v.id,
                        clinic_id=v.clinic_id,
                        summary=triage_data["summary"],
                        urgency=triage_data["urgency"],
                        crisis_flag=triage_data["crisis_flag"],
                        needs_review=triage_data["needs_review"]
                    )

                    db.session.add(triage)
                    processed_count += 1

                db.session.commit()

                if processed_count > 0:
                    print(f"✅ Triage completed for {processed_count} voicemails")

            except Exception as e:
                db.session.rollback()
                logging.error(f"❌ Worker loop error: {e}")

            # ✅ VERY IMPORTANT (CRITICAL FIX)
            time.sleep(5)
