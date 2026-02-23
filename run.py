from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user
)

print("🔥🔥🔥 THIS IS THE REAL RUN.PY 🔥🔥🔥")

import os
import logging
import secrets
from pathlib import Path
from datetime import datetime, timedelta

from billing.plans import PLANS
from utils.billing import get_clinic_usage_status

from apscheduler.schedulers.background import BackgroundScheduler
from services.digest_service import send_daily_digest

# ------------------------
# LOAD ENV
# ------------------------

from dotenv import load_dotenv
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# ------------------------
# FLASK IMPORTS
# ------------------------

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

# ------------------------
# APP SETUP
# ------------------------

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

app.config["ENABLE_AI_EXTRACTION"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ------------------------
# 🔥 LOGIN MANAGER (MOVED HERE)
# ------------------------

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.session_protection = "strong"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    from database import User
    return User.query.get(int(user_id))

# ------------------------
# DATABASE
# ------------------------

from database import db, User, Voicemail, Clinic, TriageCard
db.init_app(app)

from flask_migrate import Migrate
migrate = Migrate(app, db)

# ------------------------
# USAGE HELPER
# ------------------------

def get_clinic_usage(clinic):
    plan = PLANS.get(clinic.plan_name, PLANS["starter"])
    limit = plan["monthly_limit"]
    remaining = None if limit is None else max(limit - clinic.monthly_voicemail_used, 0)
    return {
        "plan": plan["name"],
        "used": clinic.monthly_voicemail_used,
        "limit": limit,
        "remaining": remaining,
        "overage": clinic.overage_count,
        "cycle_start": clinic.billing_cycle_start.strftime("%Y-%m-%d"),
        "cycle_end": clinic.billing_cycle_end.strftime("%Y-%m-%d"),
        "features": plan["features"]
    }

# ------------------------
# INGESTION
# ------------------------

from app.routes.ingestion import ingestion_bp
app.register_blueprint(ingestion_bp)

# ------------------------
# FILE PATHS
# ------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicecare")

# ------------------------
# AI PIPELINE
# ------------------------

def run_ai_pipeline(v, file_path):
    from utils.ai_processor import VoicemailAIProcessor
    processor = VoicemailAIProcessor()

    for attempt in range(3):
        try:
            v.update_status("transcribing")

            result = processor.transcribe_audio(file_path)
            transcript = result.get("transcription")
            confidence = result.get("confidence")

            v.transcript = transcript
            v.transcription_confidence = confidence

            v.update_status("extracting")
            patient_info = processor.extract_patient_info(transcript)

            v.update_status("summarizing")
            processor.summarize_and_triage(transcript, patient_info)

            v.update_status("completed")
            break

        except Exception as e:
            logger.error(f"AI pipeline attempt {attempt+1} failed: {e}")
            if attempt == 2:
                v.update_status("failed", failure_reason=str(e))
                raise

# ------------------------
# SCHEDULER
# ------------------------

def start_scheduler(app):
    scheduler = BackgroundScheduler()

    @scheduler.scheduled_job("cron", hour=16, minute=45)
    def daily_digest():
        with app.app_context():
            clinics = Clinic.query.all()
            for clinic in clinics:
                triage_cards = TriageCard.query.filter(
                    TriageCard.clinic_id == clinic.id,
                    TriageCard.digest_sent_at.is_(None)
                ).all()
                if not triage_cards:
                    continue
                send_daily_digest(clinic)
                for card in triage_cards:
                    card.digest_sent_at = datetime.utcnow()
                db.session.commit()

    scheduler.start()
    print("🔥 APScheduler started (digest scheduler active)")

# ------------------------
# ROUTES
# ------------------------

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/seed-clinic")
def seed_clinic():
    from database import db, Clinic

    existing = Clinic.query.first()
    if existing:
        return {"message": "Clinic already exists", "clinic_id": existing.id}

    clinic = Clinic(
        name="Default Clinic",
        email="admin@voicecare.local",
        ingest_email_token=secrets.token_hex(16),
        plan_name="starter",
        monthly_voicemail_limit=300,
        monthly_voicemail_used=0,
        billing_cycle_start=datetime.utcnow(),
        billing_cycle_end=datetime.utcnow() + timedelta(days=30),
        overage_count=0,
        is_active=True
    )

    db.session.add(clinic)
    db.session.commit()

    return {"message": "Clinic created", "clinic_id": clinic.id}

# ✅ NEW TEMP ADMIN CREATION ROUTE

@app.route("/create-admin")
def create_admin():
    from database import db, User, Clinic
    from datetime import datetime, timedelta

    existing = User.query.filter_by(email="admin@voicecare.com").first()
    if existing:
        return "Admin already exists"

    clinic = Clinic(
        name="Default Clinic",
        email="admin@voicecare.com",
        ingest_email_token=secrets.token_hex(16),
        plan_name="starter",
        monthly_voicemail_limit=300,
        monthly_voicemail_used=0,
        billing_cycle_start=datetime.utcnow(),
        billing_cycle_end=datetime.utcnow() + timedelta(days=30),
        overage_count=0,
        is_active=True
    )

    db.session.add(clinic)
    db.session.commit()

    user = User(
        email="admin@voicecare.com",
        clinic_id=clinic.id
    )
    user.set_password("Admin123!")

    db.session.add(user)
    db.session.commit()

    return "Admin user created"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email") or request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return render_template("login.html", error="Invalid credentials")
        login_user(user, remember=True)
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "success")
    return redirect(url_for("login"))

@app.route("/test-digest")
def test_digest():
    clinic = Clinic.query.first()
    if not clinic:
        return "No clinic found"
    send_daily_digest(clinic)
    return "Digest triggered"

from services.storage_service import upload_file

@app.route("/upload", methods=["POST"])
def upload_voicemail():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    clinic_id = 1

    s3_key = upload_file(file)

    voicemail = Voicemail(
        clinic_id=clinic_id,
        filename=file.filename,
        audio_url=s3_key,
        source="clinic_upload",
        received_at=datetime.utcnow(),
        status="received"
    )

    db.session.add(voicemail)
    db.session.commit()

    return jsonify({"success": True, "voicemail_id": voicemail.id}), 201

@app.route("/dashboard")
@login_required
def dashboard():
    voicemails = (
        Voicemail.query
        .filter_by(clinic_id=current_user.clinic_id)
        .order_by(Voicemail.id.desc())
        .all()
    )

    clinic = current_user.clinic
    usage = get_clinic_usage(clinic)
    usage_status = get_clinic_usage_status(clinic)

    total_voicemails = len(voicemails)
    pending_processing = Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        transcript=None
    ).count()
    processed_today = Voicemail.query.filter(
        Voicemail.clinic_id == current_user.clinic_id,
        Voicemail.transcript.isnot(None),
        Voicemail.received_at >= datetime.utcnow().date()
    ).count()

    return render_template(
        "dashboard.html",
        clinic=clinic,
        voicemails=voicemails,
        usage=usage,
        usage_status=usage_status,
        total_voicemails=total_voicemails,
        pending_processing=pending_processing,
        processed_today=processed_today
    )

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        start_scheduler(app)

    print("🚀 Flask server starting...")
    app.run(debug=True)