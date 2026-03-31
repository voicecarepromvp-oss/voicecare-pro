from datetime import date

class BillingService:

    @staticmethod
    def can_process_voicemail(clinic):

        # 1. Must be active subscription
        if clinic.subscription_status != "ACTIVE":
            return False, "Subscription inactive. Please upgrade."

        # 2. Check limit
        if clinic.monthly_voicemail_limit is None:
            return True, None  # unlimited plan

        if clinic.monthly_voicemail_used >= clinic.monthly_voicemail_limit:
            return False, "Monthly limit reached. Upgrade required."

        return True, None

    @staticmethod
    def record_usage(clinic):
        clinic.monthly_voicemail_used += 1