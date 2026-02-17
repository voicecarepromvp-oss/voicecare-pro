import os
import json
import logging
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CRISIS_KEYWORDS = [
    "suicide",
    "kill myself",
    "end my life",
    "can't go on",
    "overdose",
    "self harm",
    "panic attack emergency"
]


def detect_crisis(transcript: str) -> bool:
    lower = transcript.lower()
    return any(keyword in lower for keyword in CRISIS_KEYWORDS)


def extract_triage(transcript: str):
    """
    Existing triage logic using OpenAI.
    """

    crisis_flag = detect_crisis(transcript)

    prompt = f"""
You are assisting a psychiatric clinic.

Analyze the voicemail transcript below.

Return ONLY valid JSON with:
- summary (2-3 sentence concise summary)
- urgency ("urgent" or "non_urgent")

Mark as "urgent" if:
- medication issues
- severe distress
- same-day request
- worsening symptoms
- crisis language

Transcript:
\"\"\"{transcript}\"\"\"
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You summarize psychiatric voicemails safely."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    content = response.choices[0].message.content

    # ✅ SAFE JSON PARSING (Prevents Worker Crash)
    try:
        structured = json.loads(content)
    except Exception as e:
        logging.error(f"JSON parse failed: {e}")
        return None

    urgency = structured["urgency"]

    # Safety override
    if crisis_flag:
        urgency = "urgent"

    return {
        "summary": structured["summary"],
        "urgency": urgency,
        "crisis_flag": crisis_flag,
        "needs_review": crisis_flag
    }


# ✅ NEW FUNCTION REQUIRED BY WORKER
def analyze_transcription(transcription_text: str):
    """
    Wrapper function used by the worker.
    Returns summary, urgency_level, and crisis_flag.
    """

    result = extract_triage(transcription_text)

    if result is None:
        return None

    return {
        "summary": result["summary"],
        "urgency_level": result["urgency"],  # renamed for worker compatibility
        "crisis_flag": result["crisis_flag"]
    }
