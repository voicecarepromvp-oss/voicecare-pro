def route_voicemail(intent: str, confidence: float):
    """
    Decide department + review status based on intent and confidence
    """

    department_map = {
        "appointment_cancel": "Scheduling",
        "appointment_reschedule": "Scheduling",
        "billing": "Billing",
        "urgent_medical": "Nurse",
        "general_inquiry": "Front Desk",
    }

    department = department_map.get(intent, "Front Desk")

    needs_human_review = False
    priority = "normal"

    # Urgent always escalates
    if intent == "urgent_medical":
        priority = "high"
        needs_human_review = True
        return department, priority, needs_human_review

    # Confidence-based handling
    if confidence >= 0.85:
        needs_human_review = False
    elif confidence >= 0.60:
        needs_human_review = True
    else:
        needs_human_review = True
        department = "Human Review Queue"

    return department, priority, needs_human_review
