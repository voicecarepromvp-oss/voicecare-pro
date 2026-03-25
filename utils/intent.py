# utils/intent.py

def classify_intent(transcript: str):
    text = transcript.lower()

    rules = {
        "appointment_cancel": {
            "keywords": ["cancel", "cancellation"],
            "confidence": 0.95
        },
        "appointment_reschedule": {
            "keywords": ["reschedule", "move my appointment", "change appointment"],
            "confidence": 0.92
        },
        "appointment_schedule": {
            "keywords": ["schedule", "book appointment", "make an appointment"],
            "confidence": 0.90
        },
        "billing": {
            "keywords": ["bill", "billing", "payment", "invoice", "charge"],
            "confidence": 0.88
        },
        "prescription_refill": {
            "keywords": ["refill", "prescription", "medication"],
            "confidence": 0.93
        },
        "urgent_medical": {
            "keywords": ["urgent", "emergency", "chest pain", "shortness of breath"],
            "confidence": 0.97
        }
    }

    matched_keywords = []

    for intent, rule in rules.items():
        for keyword in rule["keywords"]:
            if keyword in text:
                matched_keywords.append(keyword)
                return {
                    "intent": intent,
                    "confidence": rule["confidence"],
                    "matched_keywords": matched_keywords
                }

    # Fallback intent
    return {
        "intent": "general_inquiry",
        "confidence": 0.50,
        "matched_keywords": []
    }
