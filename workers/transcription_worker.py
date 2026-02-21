import time
import asyncio  # ✅ Added as per mentor instruction
from datetime import datetime
from database import db, Voicemail
from utils.ai_processor import VoicemailAIProcessor
from deepgram import DeepgramClient, PrerecordedOptions
from run import app  # ✅ REQUIRED for app context


def get_next_voicemail():
    return (
        db.session.query(Voicemail)
        .filter_by(status="received")
        .order_by(Voicemail.id.asc())
        .first()
    )


def worker_loop():
    ai_processor = VoicemailAIProcessor()

    print("🚀 Worker loop running...")

    while True:
        voicemail = get_next_voicemail()

        if not voicemail:
            time.sleep(2)
            continue

        print(f"🎧 Found voicemail ID {voicemail.id}")

        try:
            # Step 1: Mark as transcribing
            voicemail.status = "transcribing"
            db.session.commit()

            # Step 2: Transcribe (S3 key stored in audio_url)
            transcript, confidence = ai_processor.transcribe_audio(
                voicemail.audio_url
            )

            # Step 3: Save transcript
            voicemail.transcript = transcript
            voicemail.transcription_confidence = confidence
            voicemail.transcribed_at = datetime.utcnow()

            # Step 4: Move to next stage
            voicemail.status = "extracting"
            db.session.commit()

            print(f"✅ Completed voicemail {voicemail.id}")

        except Exception as e:
            print(f"❌ Error processing voicemail {voicemail.id}: {e}")

            voicemail.status = "failed"
            voicemail.failure_reason = str(e)
            voicemail.last_error_at = datetime.utcnow()
            db.session.commit()

        time.sleep(1)


# ✅ ENTRY POINT + APP CONTEXT (CRITICAL FIX)
if __name__ == "__main__":
    print("🔥 Background Worker Starting...")
    with app.app_context():
        worker_loop()