import time
import asyncio
import logging
from datetime import datetime
from database import db, Voicemail
from utils.ai_processor import VoicemailAIProcessor
from run import app


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_next_voicemail():
    return (
        db.session.query(Voicemail)
        .filter_by(status="received")
        .order_by(Voicemail.id.asc())
        .first()
    )


def worker_loop():
    ai_processor = VoicemailAIProcessor()

    logger.info("🚀 Worker loop running...")

    while True:
        voicemail = get_next_voicemail()

        if not voicemail:
            time.sleep(2)
            continue

        logger.info(f"🎧 Found voicemail ID {voicemail.id}")

        try:
            # ----------------------------
            # TRANSCRIPTION
            # ----------------------------
            logger.info("Starting transcription...")
            voicemail.status = "transcribing"
            db.session.commit()

            transcript, confidence = ai_processor.transcribe_audio(
                voicemail.audio_url
            )

            logger.info("Transcription completed")

            voicemail.transcript = transcript
            voicemail.transcription_confidence = confidence
            voicemail.transcribed_at = datetime.utcnow()

            # ----------------------------
            # EXTRACTION
            # ----------------------------
            logger.info("Starting extraction...")
            voicemail.status = "extracting"
            db.session.commit()

            patient_info = ai_processor.extract_patient_info(transcript)
            logger.info("Extraction completed")

            # ----------------------------
            # SUMMARIZATION
            # ----------------------------
            logger.info("Starting summarization...")
            voicemail.status = "summarizing"
            db.session.commit()

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
            logger.error(f"❌ Pipeline failed for voicemail {voicemail.id}: {e}")

            voicemail.status = "failed"
            voicemail.failure_reason = str(e)
            voicemail.last_error_at = datetime.utcnow()
            db.session.commit()

        time.sleep(1)


if __name__ == "__main__":
    logger.info("🔥 Background Worker Starting...")
    with app.app_context():
        worker_loop()