# workers/transcription_worker.py

import sys
import os
import time
import logging
from datetime import datetime

# ----------------------------
# Fix Python path for Render
# ----------------------------
# Add repo root to Python path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ----------------------------
# Imports
# ----------------------------
from database import db, Voicemail
from utils.ai_processor import VoicemailAIProcessor
from run import app  # Flask app for context

# ✅ STEP 2.1 — ADDED IMPORTS
from services.email_service import send_email
from database import Clinic

# ----------------------------
# Logger
# ----------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ----------------------------
# Helper: Get next voicemail to process
# ----------------------------
def get_next_voicemail():
    return (
        db.session.query(Voicemail)
        .filter_by(status="received")
        .order_by(Voicemail.id.asc())
        .first()
    )

# ✅ STEP 2.2 — ADDED NOTIFICATION FUNCTION
def send_clinic_notification(voicemail):

    clinic = Clinic.query.get(voicemail.clinic_id)

    if not clinic:
        print("Clinic not found. Skipping email.")
        return

    if not clinic.email:
        print("Clinic email not configured. Skipping email.")
        return

    subject = f"New Voicemail - {voicemail.urgency_level.upper()}"

    html_content = f"""
    <h2>New Voicemail Received</h2>

    <p><strong>Summary:</strong> {voicemail.summary}</p>
    <p><strong>Urgency:</strong> {voicemail.urgency_level}</p>
    <p><strong>Triage Category:</strong> {voicemail.triage_category}</p>

    <hr>

    <p><strong>Patient Name:</strong> {voicemail.patient_name}</p>
    <p><strong>Phone:</strong> {voicemail.patient_phone}</p>

    <hr>

    <p><strong>Recommended Action:</strong></p>
    <p>{voicemail.recommended_action}</p>

    <hr>

    <p><strong>Full Transcript:</strong></p>
    <p>{voicemail.transcript}</p>
    """

    success = send_email(clinic.email, subject, html_content)

    if success:
        print(f"✅ Notification email sent to {clinic.email}")
    else:
        print("❌ Email sending failed.")

# ----------------------------
# Main worker loop
# ----------------------------
def worker_loop():
    logger.info("🔥 Background Worker Starting...")
    ai_processor = VoicemailAIProcessor()
    logger.info("🚀 Worker loop running...")

    while True:
        with app.app_context():
            voicemail = get_next_voicemail()

            if not voicemail:
                time.sleep(2)
                continue

            logger.info(f"🎧 Found voicemail ID {voicemail.id}")

            try:
                # ----------------------------
                # TRANSCRIPTION
                # ----------------------------
                logger.info("📝 Starting transcription...")
                voicemail.status = "transcribing"
                db.session.commit()

                transcript, confidence = ai_processor.transcribe_audio(voicemail.audio_url)
                logger.info(f"✅ Transcription completed: {len(transcript)} chars, confidence={confidence}")

                voicemail.transcript = transcript
                voicemail.transcription_confidence = confidence
                voicemail.transcribed_at = datetime.utcnow()

                # ----------------------------
                # EXTRACTION
                # ----------------------------
                logger.info("🔍 Starting patient info extraction...")
                voicemail.status = "extracting"
                db.session.commit()

                patient_info = ai_processor.extract_patient_info(transcript)
                logger.info(f"✅ Extraction completed: {patient_info}")

                # ----------------------------
                # SUMMARIZATION & TRIAGE
                # ----------------------------
                logger.info("🧠 Starting summarization & triage...")
                voicemail.status = "summarizing"
                db.session.commit()

                summary_data = ai_processor.summarize_and_triage(transcript, patient_info)
                logger.info(f"✅ Summarization completed: {summary_data}")

                # ----------------------------
                # SAVE RESULTS
                # ----------------------------
                if summary_data.get("success"):
                    voicemail.summary = summary_data.get("summary")
                    voicemail.triage_category = summary_data.get("department_routing")
                    voicemail.urgency_level = summary_data.get("urgency_level")

                voicemail.status = "completed"
                db.session.commit()

                # ✅ STEP 2.3 — CALL NOTIFICATION AFTER COMPLETION
                send_clinic_notification(voicemail)

                logger.info(f"🏁 Voicemail {voicemail.id} fully completed")

            except Exception as e:
                logger.error(f"❌ Pipeline failed for voicemail {voicemail.id}: {e}", exc_info=True)
                voicemail.status = "failed"
                voicemail.failure_reason = str(e)
                voicemail.last_error_at = datetime.utcnow()
                db.session.commit()

            time.sleep(1)  # small delay before next voicemail

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    with app.app_context():
        worker_loop()