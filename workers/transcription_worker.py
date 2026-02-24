import time
import logging
from datetime import datetime

from database import db, Voicemail
from utils.ai_processor import VoicemailAIProcessor
from run import app


# ----------------------------------
# LOGGING SETUP
# ----------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ----------------------------------
# FETCH NEXT VOICEMAIL
# ----------------------------------
def get_next_voicemail():
    return (
        db.session.query(Voicemail)
        .filter_by(status="received")
        .order_by(Voicemail.id.asc())
        .first()
    )


# ----------------------------------
# MAIN WORKER LOOP
# ----------------------------------
def worker_loop():
    logger.info("🚀 Worker loop initialized")

    ai_processor = VoicemailAIProcessor()

    while True:
        try:
            voicemail = get_next_voicemail()

            if not voicemail:
                time.sleep(2)
                continue

            logger.info(f"🎧 Processing voicemail ID {voicemail.id}")

            # ----------------------------
            # TRANSCRIPTION
            # ----------------------------
            voicemail.status = "transcribing"
            db.session.commit()

            logger.info("Starting transcription...")
            transcript, confidence = ai_processor.transcribe_audio(
                voicemail.audio_url
            )
            logger.info("Transcription completed")

            voicemail.transcript = transcript
            voicemail.transcription_confidence = confidence
            voicemail.transcribed_at = datetime.utcnow()
            db.session.commit()

            # ----------------------------
            # EXTRACTION
            # ----------------------------
            voicemail.status = "extracting"
            db.session.commit()

            logger.info("Starting extraction...")
            patient_info = ai_processor.extract_patient_info(transcript)
            logger.info("Extraction completed")

            # ----------------------------
            # SUMMARIZATION
            # ----------------------------
            voicemail.status = "summarizing"
            db.session.commit()

            logger.info("Starting summarization...")
            summary_data = ai_processor.summarize_and_triage(
                transcript,
                patient_info
            )
            logger.info("Summarization completed")

            # ----------------------------
            # SAVE RESULTS
            # ----------------------------
            if summary_data.get("success"):
                voicemail.summary = summary_data.get("summary")
                voicemail.triage_category = summary_data.get("department_routing")
                voicemail.urgency_level = summary_data.get("urgency_level")

            voicemail.status = "completed"
            db.session.commit()

            logger.info(f"✅ Voicemail {voicemail.id} fully completed")

        except Exception as e:
            logger.error(f"❌ Pipeline failed: {str(e)}")

            db.session.rollback()

            if "voicemail" in locals() and voicemail:
                voicemail.status = "failed"
                voicemail.failure_reason = str(e)
                voicemail.last_error_at = datetime.utcnow()
                db.session.commit()

        time.sleep(1)


# ----------------------------------
# ENTRY POINT
# ----------------------------------
if __name__ == "__main__":
    logger.info("🔥 Background Worker Starting...")

    with app.app_context():
        worker_loop()