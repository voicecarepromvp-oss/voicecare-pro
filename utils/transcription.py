import certifi
import os

os.environ["SSL_CERT_FILE"] = certifi.where()

import os
import asyncio
from deepgram import Deepgram

def transcribe_voicemail(file_path: str) -> str:
    print("🎧 Opening audio file:", file_path)

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set")

    dg = Deepgram(api_key)

    async def run_transcription():
        with open(file_path, "rb") as audio:
            source = {"buffer": audio, "mimetype": "audio/mpeg"}

            return await dg.transcription.prerecorded(
                source,
                {
                    "model": "nova-2",
                    "smart_format": True,
                    "language": "en-US"
                }
            )

    response = asyncio.run(run_transcription())

    print("📦 Raw Deepgram response received")

    return response["results"]["channels"][0]["alternatives"][0]["transcript"]
