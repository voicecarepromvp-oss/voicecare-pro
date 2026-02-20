from services.transcription_status import update_voicemail_status
from database import db, Voicemail

import os
import json
import logging

from services.storage_service import generate_presigned_url


# ✅ Retry Error Classifier
def is_retryable_error(e):
    error_str = str(e).lower()
    return any([
        "429" in error_str,
        "rate limit" in error_str,
        "timeout" in error_str,
        "temporarily unavailable" in error_str,
        "connection reset" in error_str,
        "service unavailable" in error_str
    ])


class VoicemailAIProcessor:
    """Handle AI processing of voicemails with robust error handling"""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY not found in environment")

    # ============================================================
    # ✅ TRANSCRIPTION (DEEPGRAM v5 - nova-2-medical)
    # ============================================================

    def transcribe_audio(self, s3_key):
        """
        Transcribe audio from S3 using Deepgram v5
        Returns: (transcript, confidence)
        """

        from deepgram import DeepgramClient

        client = DeepgramClient(self.api_key)

        # Generate temporary presigned S3 URL (1 hour lifetime)
        audio_url = generate_presigned_url(s3_key)

        options = {
            "model": "nova-2-medical",
            "punctuate": True,
            "diarize": False,
            "smart_format": True,
            "language": "en"
        }

        response = client.listen.prerecorded.v("1").transcribe_url(
            {"url": audio_url},
            options
        )

        transcript = response.results.channels[0].alternatives[0].transcript
        confidence = response.results.channels[0].alternatives[0].confidence

        return transcript, confidence

    # ============================================================
    # PATIENT INFO EXTRACTION
    # ============================================================

    def extract_patient_info(self, transcription):
        """Extract patient information from transcription"""
        try:
            prompt = f"""
            Extract patient information from this healthcare voicemail transcription. Return JSON only.

            Transcription: "{transcription}"

            Extract and return in this exact JSON format:
            {{
                "patient_name": "Full name or null",
                "patient_dob": "Date of birth (MM/DD/YYYY format) or null",
                "patient_phone": "Phone number or null",
                "call_reason": "Brief reason for call or null"
            }}
            """

            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )

            result_text = response.choices[0].message.content.strip()

            try:
                result = json.loads(result_text)
            except Exception:
                logging.warning(f"Patient info JSON parse failed. Raw response: {result_text}")
                result = {}

            return {
                'success': True,
                'patient_name': result.get('patient_name'),
                'patient_dob': result.get('patient_dob'),
                'patient_phone': result.get('patient_phone'),
                'call_reason': result.get('call_reason')
            }

        except Exception as e:
            logging.error(f"Error extracting patient info: {e}")
            return {
                'success': False,
                'error': str(e),
                'patient_name': None,
                'patient_dob': None,
                'patient_phone': None,
                'call_reason': None
            }

    # ============================================================
    # SUMMARY + TRIAGE
    # ============================================================

    def summarize_and_triage(self, transcription, patient_info):
        """Create summary and determine triage routing"""
        logging.info("🔥 AI summarize_and_triage() CALLED")

        try:
            prompt = f"""
            Analyze this healthcare voicemail for summarization and triage routing.

            Transcription: "{transcription}"

            Patient Info:
            - Name: {patient_info.get('patient_name', 'Unknown')}
            - Reason: {patient_info.get('call_reason', 'Not specified')}

            Provide response in this JSON format:
            {{
                "summary": "2-3 sentence summary of the call",
                "urgency_level": "low|medium|high|urgent",
                "recommended_action": "What should be done next",
                "department_routing": "Which department should handle this"
            }}
            """

            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=300
            )

            raw_text = response.choices[0].message.content.strip()
            logging.info(f"📄 RAW OpenAI response: {raw_text}")

            try:
                result = json.loads(raw_text)
            except Exception:
                logging.warning("Triage JSON parse failed. Marking needs_review.")
                result = {
                    "summary": "Error processing voicemail",
                    "urgency_level": "medium",
                    "recommended_action": "Manual review required",
                    "department_routing": "Administration"
                }

            return {
                'success': True,
                'summary': result.get('summary'),
                'urgency_level': result.get('urgency_level'),
                'recommended_action': result.get('recommended_action'),
                'department_routing': result.get('department_routing')
            }

        except Exception as e:
            logging.error(f"Error in summarization/triage: {e}")
            return {
                'success': False,
                'summary': "Error processing voicemail",
                'urgency_level': 'medium',
                'recommended_action': 'Manual review required',
                'department_routing': 'Administration'
            }

    # ============================================================
    # COMPLETE PIPELINE
    # ============================================================

    def process_voicemail_complete(self, voicemail, s3_key):
        """Complete AI processing pipeline with safe DB commit"""

        results = {
            'transcription_result': None,
            'patient_info': None,
            'triage_result': None,
            'overall_success': False
        }

        try:
            logging.info(f"🚀 AI PIPELINE STARTED → voicemail: {voicemail.id}")

            update_voicemail_status(voicemail.id, "transcribing")

            transcript, confidence = self.transcribe_audio(s3_key)

            results['transcription_result'] = {
                "transcription": transcript,
                "confidence": confidence
            }

            patient_info = self.extract_patient_info(transcript)
            results['patient_info'] = patient_info

            triage_result = self.summarize_and_triage(transcript, patient_info)
            results['triage_result'] = triage_result

            voicemail.transcript = transcript
            voicemail.transcription_confidence = confidence
            voicemail.transcription_provider = "deepgram_v5"

            if triage_result.get("success"):
                voicemail.summary = triage_result.get("summary")
                voicemail.triage_category = triage_result.get("department_routing")
                voicemail.urgency_level = triage_result.get("urgency_level")

            db.session.commit()

            if confidence < 0.75 or not triage_result.get("success"):
                update_voicemail_status(voicemail.id, "needs_review")
            else:
                update_voicemail_status(voicemail.id, "completed")

            results['overall_success'] = True
            logging.info(f"✅ FINAL STATUS → {voicemail.status}")

            return results

        except Exception as e:
            logging.error(f"Pipeline error: {e}")
            db.session.rollback()
            update_voicemail_status(voicemail.id, "needs_review", str(e))
            return results
