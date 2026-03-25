# utils/summarize_and_triage.py
import os
import json
import re
import logging
import openai
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

logger = logging.getLogger(__name__)

CATEGORIES = ["Scheduling", "Refill", "Urgent", "General"]

PROMPT = """
You are a medical admin assistant. Given the voicemail transcript, return ONLY a JSON object with:
- summary: 1-2 sentence concise summary.
- category: one of ["Scheduling","Refill","Urgent","General"].
- confidence: 0-1 float (two decimals).
- reason: one short sentence why that category.

TRANSCRIPT:
{transcript}
"""

def summarize_and_triage(transcript: str, model: str = "gpt-3.5-turbo") -> dict:
    if not transcript:
        raise ValueError("Empty transcript")

    prompt = PROMPT.format(transcript=transcript.strip())
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise medical admin assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=300
        )
        content = response["choices"][0]["message"]["content"]
        # extract JSON substring
        m = re.search(r"\{[\s\S]*\}", content)
        json_text = m.group(0) if m else content
        data = json.loads(json_text)
        cat = data.get("category", "").strip()
        if cat not in CATEGORIES:
            # fallback
            for c in CATEGORIES:
                if c.lower() in cat.lower():
                    cat = c
                    break
            else:
                cat = "General"
        return {
            "summary": data.get("summary"),
            "category": cat,
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason")
        }
    except Exception as e:
        logger.exception("Summarization/triage failed: %s", e)
        return {"summary": None, "category": None, "confidence": 0.0, "reason": str(e)}
