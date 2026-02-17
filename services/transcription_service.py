# services/transcription_service.py
import openai
from pathlib import Path
from run import logger

# Make sure your OPENAI_API_KEY is set in .env
# e.g., export OPENAI_API_KEY="sk-..."

def transcribe_audio(filename: str):
    """
    Transcribe an audio file using OpenAI Whisper (v1+ SDK)
    Returns: transcript (str), confidence (None, not provided by API)
    """
    file_path = Path("uploads") / filename

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    logger.debug(f"DEBUG: Transcribing file at {file_path}")

    try:
        with open(file_path, "rb") as f:
            response = openai.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )

        transcript = response.text
        confidence = None  # Whisper API v1 does not return confidence

        logger.debug(f"DEBUG: Transcription completed for {filename}")
        return transcript, confidence

    except Exception as e:
        logger.error(f"Transcription failed for {filename}: {e}")
        raise