import os
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def send_email(to_email, subject, html_content):
    """
    Sends an email using SendGrid.
    Returns True on success, False on failure.
    """

    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL")

    # Safety check — fail fast if environment variables missing
    if not api_key:
        logging.error("SENDGRID_API_KEY is not set.")
        return False

    if not from_email:
        logging.error("FROM_EMAIL is not set.")
        return False

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        logging.info(f"Email sent. Status code: {response.status_code}")

        # Optional: Only log detailed response in development
        if os.getenv("FLASK_ENV") == "development":
            logging.debug(f"SendGrid response headers: {response.headers}")

        return response.status_code in [200, 202]

    except Exception as e:
        logging.error(f"SendGrid error: {str(e)}")
        return False