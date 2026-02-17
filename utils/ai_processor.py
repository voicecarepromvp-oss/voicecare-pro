from services.transcription_status import update_voicemail_status
from database import db, Voicemail

import os
import time
import json
import logging


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
        self.api_key = api_key or os.getenv('DEEPGRAM_API_KEY')

    # ============================================================
    # TRANSCRIPTION
    # ============================================================

    def transcribe_audio(self, file_path):
        """Transcribe audio using Deepgram"""
        try:
            from deepgram import Deepgram

            dg = Deepgram(self.api_key)

            with open(file_path, "rb") as audio:
                source = {"buffer": audio, "mimetype": "audio/wav"}

                options = {
                    "model": "nova-2-medical",
                    "punctuate": True,
                    "diarize": False,
                    "smart_format": True,
                    "language": "en"
                }

                response = dg.transcription.sync_prerecorded(source, options)

            transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]
            confidence = response["results"]["channels"][0]["alternatives"][0].get("confidence", 0.85)

            return {
                "success": True,
                "transcription": transcript,
                "confidence": confidence,
                "language": "en"
            }

        except Exception as e:
            logging.error(f"Transcription error: {e}")
            return {
                "success": False,
                "error": str(e),
                "transcription": None
            }

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

            # ✅ Safe JSON parse
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
    # SUMMARY + TRIAGE (OPENAI)
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

            # ✅ Safe JSON parse
            try:
                result = json.loads(raw_text)
            except Exception:
                logging.warning(f"Triage JSON parse failed. Marking needs_review. Raw: {raw_text}")
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

    def process_voicemail_complete(self, voicemail, file_path):
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

            transcription_result = self.transcribe_audio(file_path)
            results['transcription_result'] = transcription_result

            if not transcription_result['success']:
                update_voicemail_status(
                    voicemail.id,
                    "failed",
                    failure_reason=transcription_result.get("error")
                )
                return results

            transcription = transcription_result['transcription']
            confidence = transcription_result.get("confidence", 1.0)

            patient_info = self.extract_patient_info(transcription)
            results['patient_info'] = patient_info

            triage_result = self.summarize_and_triage(transcription, patient_info)
            results['triage_result'] = triage_result

            # ✅ Update voicemail fields
            voicemail.transcript = transcription
            voicemail.transcription_confidence = confidence
            voicemail.transcription_provider = "deepgram"

            if triage_result.get("success"):
                voicemail.summary = triage_result.get("summary")
                voicemail.triage_category = triage_result.get("department_routing")
                voicemail.urgency_level = triage_result.get("urgency_level")

            try:
                db.session.commit()
            except Exception as e:
                logging.error(f"DB commit failed: {e}. Rolling back session.")
                db.session.rollback()
                update_voicemail_status(voicemail.id, "needs_review")
                return results

            # Final status
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