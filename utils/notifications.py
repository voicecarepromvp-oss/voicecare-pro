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
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        print("⚠️ SMTP email not configured — skipping email")
        return

    department = voicemail_data.get("department", "Unknown")
    to_email = DEPARTMENT_EMAILS.get(department, SMTP_EMAIL)

    subject = f"[VoiceCare Pro] New Voicemail — {department}"

    body = f"""
New voicemail received and routed automatically.

📞 Transcript:
{voicemail_data.get("transcript")}

🧠 AI Analysis:
• Intent: {voicemail_data.get("intent")}
• Confidence: {voicemail_data.get("confidence")}
• Priority: {voicemail_data.get("priority")}
• Needs Human Review: {voicemail_data.get("needs_human_review")}

— VoiceCare Pro
"""

    msg = EmailMessage()
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent successfully → {to_email}")

    except Exception as e:
        print("❌ Email failed:", str(e))
