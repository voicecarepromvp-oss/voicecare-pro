# workers/transcription_worker.py

import sys
import os
import time
import logging
import traceback
from datetime import datetime

# ----------------------------
# Fix Python path for Render
# ----------------------------
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ----------------------------
# Imports
# ----------------------------
from database import db, Voicemail, Clinic
from utils.ai_processor import VoicemailAIProcessor
from run import app  # Flask app for context
from flask import render_template
from services.email_service import send_email

# ----------------------------
# Logger
# ----------------------------
logger = logging.getLogger("voicecare")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# ----------------------------
# Helper: Get next voicemail to process
# ----------------------------
def get_next_voicemail():
    return (
        db.session.query(Voicemail)
        .filter(Voicemail.status.in_(["pending", "received"]))
        .order_by(Voicemail.id.asc())
        .first()
    )

# ----------------------------
# Safe email notification
# ----------------------------
def send_clinic_notification(voicemail):
    try:
        clinic = Clinic.query.get(voicemail.clinic_id)
        if not clinic or not clinic.email:
            logger.warning(f"Clinic or email missing for voicemail {voicemail.id}")
            return

        subject = f"New Voicemail - {(voicemail.urgency_level or 'unknown').upper()}"

        dashboard_link = f"https://getvoicecarepro.com/voicemail/{voicemail.id}"

        html_content = render_template(
         "email_voicemail.html",
          voicemail=voicemail,
          dashboard_link=dashboard_link
        )
        
        success = send_email(clinic.email, subject, html_content)
        if success:
            logger.info(f"✅ Notification email sent to {clinic.email}")
        else:
            logger.error(f"❌ Email sending failed for {clinic.email}")
    except Exception:
        logger.error(f"❌ Failed sending email for voicemail {voicemail.id}:\n{traceback.format_exc()}")

# ----------------------------
# Main worker loop (safe)
# ----------------------------
def worker_loop():
    logger.info("🔥 Background Worker Starting...")
    ai_processor = VoicemailAIProcessor()
    logger.info("🚀 Worker loop running...")

    while True:
        try:
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

                    #-----------------------------
                    # AI ROUTING CLASSIFICATION
                    #-----------------------------
                    routing = ai_processor.classify_voicemail_action(transcript)

                    voicemail.department = routing.get("department")
                    voicemail.recommended_action = routing.get("recommended_action")
                    voicemail.priority = routing.get("priority")

                    logger.info(
                        f"AI Routing → Dept: {voicemail.department}, "
                        f"Action: {voicemail.recommended_action}, "
                        f"Priority: {voicemail.priority}"
                    )

                    # ----------------------------
                    # PATIENT INFO EXTRACTION
                    # ----------------------------
                    logger.info("🔍 Starting patient info extraction...")
                    voicemail.status = "extracting"
                    db.session.commit()

                    patient_info = ai_processor.extract_patient_info(transcript)
                    logger.info(f"✅ Extraction completed: {patient_info}")

                    if patient_info.get("success"):
                        voicemail.patient_name = patient_info.get("patient_name")
                        voicemail.patient_phone = patient_info.get("patient_phone")
                        voicemail.patient_dob = patient_info.get("patient_dob")
                        voicemail.call_reason = patient_info.get("call_reason")

                    db.session.commit()

                    # ----------------------------
                    # SUMMARIZATION & TRIAGE
                    # ----------------------------
                    logger.info("🧠 Starting summarization & triage...")
                    voicemail.status = "summarizing"
                    db.session.commit()

                    summary_data = ai_processor.summarize_and_triage(transcript, patient_info)
                    logger.info(f"✅ Summarization completed: {summary_data}")

                    if summary_data.get("success"):
                        voicemail.summary = summary_data.get("summary")
                        voicemail.triage_category = summary_data.get("department_routing")
                        voicemail.urgency_level = summary_data.get("urgency_level")

                    voicemail.status = "completed"
                    db.session.commit()

                    # ----------------------------
                    # Notify Clinic
                    # ----------------------------
                    send_clinic_notification(voicemail)
                    logger.info(f"🏁 Voicemail {voicemail.id} fully completed")

                except Exception as e:
                    logger.error(f"❌ Pipeline failed for voicemail {voicemail.id}:\n{traceback.format_exc()}")

                    # Increment retry count
                    voicemail.retry_count = (voicemail.retry_count or 0) + 1
                    voicemail.failure_reason = str(e)
                    voicemail.failure_error_at = datetime.utcnow()

                    if voicemail.retry_count >= 3:
                        voicemail.status = "failed"
                        logger.error(f"Voicemail {voicemail.id} permanently failed after 3 attempts")

                    else:
                        voicemail.status = "pending"
                        logger.info(f"Retry attempt {voicemail.retry_count} scheduled for voicemail {voicemail.id}")

                    db.session.commit()

            time.sleep(1)

        except Exception:
            # Catch **any error outside single voicemail**
            logger.critical(f"❌ Worker crashed outside voicemail loop:\n{traceback.format_exc()}")
            time.sleep(5)  # wait and retry

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    with app.app_context():
        worker_loop()