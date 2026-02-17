# utils/billing.py

def get_clinic_usage_status(clinic):
    """
    Returns usage health for a clinic.
    Does NOT modify database.
    """

    used = clinic.monthly_voicemail_used or 0
    limit = clinic.monthly_voicemail_limit or 0

    # Enterprise / unlimited plan
    if limit == 0:
        return {
            "status": "unlimited",
            "percentage_used": 0
        }

    percentage = used / limit

    if percentage >= 1:
        return {
            "status": "limit_exceeded",
            "percentage_used": round(percentage, 2)
        }
    elif percentage >= 0.8:
        return {
            "status": "approaching_limit",
            "percentage_used": round(percentage, 2)
        }
    else:
        return {
            "status": "healthy",
            "percentage_used": round(percentage, 2)
        }
