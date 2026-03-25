def route_voicemail(intent: str) -> dict:
    """
    Decide what to do with the voicemail.
    """

    routes = {
        "emergency": {
            "priority": "HIGH",
            "department": "Doctor / Nurse",
            "action": "Immediate callback"
        },
        "appointment": {
            "priority": "NORMAL",
            "department": "Front Desk",
            "action": "Schedule appointment"
        },
        "medication": {
            "priority": "NORMAL",
            "department": "Clinical Staff",
            "action": "Refill request"
        },
        "billing": {
            "priority": "LOW",
            "department": "Billing",
            "action": "Billing follow-up"
        },
        "records": {
            "priority": "LOW",
            "department": "Admin",
            "action": "Send records"
        },
        "general": {
            "priority": "LOW",
            "department": "Front Desk",
            "action": "General inquiry"
        }
    }

    return routes.get(intent, routes["general"])
