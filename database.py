from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import logging

db = SQLAlchemy()
logger = logging.getLogger(__name__)

# ============================================================
# AUTHORITATIVE VOICEMAIL LIFECYCLE STATUSES (SINGLE SOURCE)
# ============================================================

VOICEMAIL_STATUSES = {
    "received",
    "queued",
    "transcribing",
    "extracting",
    "summarizing",
    "triaging",
    "completed",
    "failed",
    "needs_review",
}

# --------------------
# Clinic Model
# --------------------

class Clinic(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255))

    ingest_email_token = db.Column(db.String(64), unique=True, nullable=False)

    plan_name = db.Column(db.String(50), default="starter")
    monthly_voicemail_limit = db.Column(db.Integer, default=300)
    monthly_voicemail_used = db.Column(db.Integer, default=0)

    billing_cycle_start = db.Column(db.DateTime, default=datetime.utcnow)
    billing_cycle_end = db.Column(
        db.DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=30)
    )

    overage_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    users = db.relationship("User", backref="clinic", lazy=True)
    voicemails = db.relationship("Voicemail", backref="clinic", lazy=True)

    def __repr__(self):
        return f"<Clinic {self.name}>"


# --------------------
# User Model
# --------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(50), default="user")
    is_admin = db.Column(db.Boolean, default=False)

    clinic_id = db.Column(db.Integer, db.ForeignKey("clinic.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_system_admin(self):
        return self.is_admin is True

    def __repr__(self):
        return f"<User {self.email}>"


# --------------------
# Voicemail Model
# --------------------

class Voicemail(db.Model):
    __tablename__ = "voicemails"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinic.id"),
        nullable=False
    )

    filename = db.Column(db.String(255), nullable=False)
    audio_url = db.Column(db.String(255), nullable=True)
    audio_duration = db.Column(db.Integer, nullable=True)

    source = db.Column(db.String(50), nullable=False)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)

    status = db.Column(
        db.String(32),
        nullable=False,
        default="received"
    )

    # Retry Metadata
    retry_count = db.Column(db.Integer, default=0)
    last_error_at = db.Column(db.DateTime, nullable=True)

    transcript = db.Column(db.Text, nullable=True)
    transcription_confidence = db.Column(db.Float, nullable=True)
    transcription_provider = db.Column(db.String(50), nullable=True)
    transcribed_at = db.Column(db.DateTime, nullable=True)
    failure_reason = db.Column(db.Text, nullable=True)

    # ============================================================
    # Phase 3 Fields (NEW)
    # ============================================================

    summary = db.Column(db.Text, nullable=True)
    triage_category = db.Column(db.String(100), nullable=True)
    urgency_level = db.Column(db.String(50), nullable=True)

    # ============================================================
    # CENTRALIZED STATUS TRANSITION METHOD
    # ============================================================

    def update_status(self, new_status, failure_reason=None):
        """
        Centralized voicemail status update.
        Handles logging, timestamps, and failure tracking.
        """

        if new_status not in VOICEMAIL_STATUSES:
            raise ValueError(f"Invalid voicemail status: {new_status}")

        logger.info(
            f"Voicemail {self.id} status change: {self.status} → {new_status}"
        )

        self.status = new_status

        # Handle failure metadata
        if new_status == "failed":
            self.last_error_at = datetime.utcnow()
            if failure_reason:
                self.failure_reason = failure_reason
        else:
            # Clear failure info on non-failed states
            self.failure_reason = None

        db.session.commit()

    def __repr__(self):
        return f"<Voicemail {self.id}>"


# --------------------
# TriageCard Model
# --------------------

class TriageCard(db.Model):
    __tablename__ = "triage_cards"

    id = db.Column(db.Integer, primary_key=True)

    voicemail_id = db.Column(
        db.Integer,
        db.ForeignKey("voicemails.id"),
        nullable=False,
        unique=True
    )

    clinic_id = db.Column(
        db.Integer,
        db.ForeignKey("clinic.id"),
        nullable=False
    )

    summary = db.Column(db.Text, nullable=False)

    urgency = db.Column(
        db.String(20),
        nullable=False
    )

    crisis_flag = db.Column(db.Boolean, default=False)

    needs_review = db.Column(db.Boolean, default=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    # ✅ UPDATED: Timestamp-based digest tracking
    digest_sent_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<TriageCard {self.id}>"


# --------------------
# ✅ New DigestLog Model
# --------------------

class DigestLog(db.Model):
    __tablename__ = "digest_logs"

    id = db.Column(db.Integer, primary_key=True)

    clinic_id = db.Column(db.Integer, nullable=False)

    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    total_voicemails = db.Column(db.Integer)

    urgent_count = db.Column(db.Integer)

    non_urgent_count = db.Column(db.Integer)

    status = db.Column(db.String(20))  # "success" or "failed"

    error_message = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<DigestLog {self.id}>"
