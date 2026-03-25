import os
import smtplib
from email.message import EmailMessage

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

print("SMTP_EMAIL =", SMTP_EMAIL)
print("SMTP_PASSWORD =", "SET" if SMTP_PASSWORD else None)

# Department → Email routing
DEPARTMENT_EMAILS = {
    "Scheduling": SMTP_EMAIL,
    "Billing": SMTP_EMAIL,
    "Clinical": SMTP_EMAIL,
    "Front Desk": SMTP_EMAIL,
    "Unknown": SMTP_EMAIL
}

def send_routing_email(voicemail_data):
    """
    Legacy SMTP notification system (DISABLED).
    VoiceCare Pro now uses SendGrid + HTML templates via the worker.
    """
    print("⚠️ Legacy SMTP notification system disabled. Using SendGrid worker instead.")
    return