from datetime import date
from sqlalchemy import or_
from database import db, TriageCard, DigestLog
from services.email_service import send_email
import logging


def send_daily_digest(clinic):
    """
    Generates and sends a daily voicemail digest for a clinic.
    Sends email only if unsent triage cards exist.
    Includes urgent voicemails even if not from today.
    Logs an urgent safeguard message if any urgent voicemails exist.
    Creates a DigestLog entry for each attempt.
    """

    today = date.today()

    # ✅ Production-Safe Urgent Safeguard Query (STEP 23.4)
    triage_cards = (
        TriageCard.query
        .filter(TriageCard.clinic_id == clinic.id)
        .filter(TriageCard.digest_sent_at.is_(None))  # only unsent
        .filter(
            or_(
                db.func.date(TriageCard.created_at) == today,
                TriageCard.urgency == "urgent"
            )
        )
        .all()
    )

    if not triage_cards:
        logging.info(f"No triage cards eligible for digest for clinic {clinic.id}")
        return

    # -----------------------------
    # URGENT SAFEGUARD CHECK
    # -----------------------------
    urgent_exists = any(t.urgency == "urgent" for t in triage_cards)
    if urgent_exists:
        print("URGENT VOICEMAIL PRESENT IN DIGEST")
        logging.warning(f"URGENT VOICEMAIL PRESENT for clinic {clinic.id}")

    # Compute metrics
    urgent_count = len([t for t in triage_cards if t.urgency == "urgent"])
    non_urgent_count = len([t for t in triage_cards if t.urgency == "non_urgent"])

    # Build email body (plain-text)
    body = "VoiceCare Pro — Daily Voicemail Summary\n\n"
    body += f"Total New Voicemails: {len(triage_cards)}\n\n"

    if urgent_count > 0:
        body += f"URGENT ({urgent_count})\n"
        body += "-" * 30 + "\n"
        for t in triage_cards:
            if t.urgency == "urgent":
                body += f"- {t.summary}\n\n"

    if non_urgent_count > 0:
        body += f"NON-URGENT ({non_urgent_count})\n"
        body += "-" * 30 + "\n"
        for t in triage_cards:
            if t.urgency == "non_urgent":
                body += f"- {t.summary}\n\n"

    subject = f"VoiceCare Pro — {len(triage_cards)} New Voicemails"

    # ------------------------
    # Wrap sending in DigestLog
    # ------------------------
    try:
        success = send_email(clinic.email, subject, body)

        log = DigestLog(
            clinic_id=clinic.id,
            total_voicemails=len(triage_cards),
            urgent_count=urgent_count,
            non_urgent_count=non_urgent_count,
            status="success" if success else "failed"
        )

        db.session.add(log)

        # ✅ Mark triage cards as sent
        for t in triage_cards:
            t.digest_sent_at = db.func.now()

        db.session.commit()

        if success:
            logging.info(f"Daily digest sent successfully for clinic {clinic.id}")
        else:
            logging.error(f"Daily digest FAILED for clinic {clinic.id}")

    except Exception as e:
        log = DigestLog(
            clinic_id=clinic.id,
            total_voicemails=len(triage_cards),
            urgent_count=urgent_count,
            non_urgent_count=non_urgent_count,
            status="failed",
            error_message=str(e)
        )

        db.session.add(log)
        db.session.commit()

        logging.error(f"Digest generation error for clinic {clinic.id}: {str(e)}")
        raise e  # preserve original error behavior
