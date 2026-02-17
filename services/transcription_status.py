from database import db, Voicemail

def update_voicemail_status(voicemail_id, new_status, failure_reason=None):
    voicemail = Voicemail.query.get(voicemail_id)

    if not voicemail:
        raise ValueError("Voicemail not found")

    voicemail.update_status(
        new_status=new_status,
        failure_reason=failure_reason
    )

    db.session.commit()


def get_next_voicemail():
    """
    Fetches the next voicemail in deterministic order (lowest ID first)
    with status='received'.
    Also prints debug info about all received voicemails.
    """
    all_received = db.session.query(Voicemail).filter_by(status="received").all()
    print(f"DEBUG: Found {len(all_received)} voicemails with status='received'")

    # Fetch next voicemail in order
    v = db.session.query(Voicemail).filter_by(status="received").order_by(Voicemail.id.asc()).first()
    return v