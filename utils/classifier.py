def classify_intent(transcript: str) -> str:
    """
    Rule-based + keyword classifier (fast, cheap, reliable).
    Later we can upgrade to Azure OpenAI.
    """

    text = transcript.lower()

    if any(word in text for word in ["chest pain", "difficulty breathing", "emergency", "urgent", "bleeding"]):
        return "emergency"

    if any(word in text for word in ["appointment", "schedule", "reschedule", "cancel", "book"]):
        return "appointment"

    if any(word in text for word in ["refill", "medication", "prescription", "pharmacy"]):
        return "medication"

    if any(word in text for word in ["bill", "billing", "insurance", "payment", "copay"]):
        return "billing"

    if any(word in text for word in ["records", "medical records", "documents", "report"]):
        return "records"

    return "general"
