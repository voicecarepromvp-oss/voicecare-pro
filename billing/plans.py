# billing/plans.py

PLANS = {
    "starter": {
        "name": "Starter",
        "monthly_limit": 300,
        "overage_allowed": True,
        "features": [
            "voicemail_transcription",
            "intent_detection",
            "email_routing",
            "admin_dashboard"
        ]
    },

    "pro": {
        "name": "Pro",
        "monthly_limit": 1500,
        "overage_allowed": True,
        "features": [
            "voicemail_transcription",
            "intent_detection",
            "email_routing",
            "admin_dashboard",
            "priority_routing",
            "advanced_filters"
        ]
    },

    "enterprise": {
        "name": "Enterprise",
        "monthly_limit": None,  # Unlimited / contract-based
        "overage_allowed": True,
        "features": [
            "everything"
        ]
    }
}
