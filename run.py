# ------------------------
# IMPORTS
# ------------------------

import os
import logging
import secrets
import uuid
from pathlib import Path
from datetime import datetime, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify
)

from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user
)

from apscheduler.schedulers.background import BackgroundScheduler
from services.digest_service import send_daily_digest
from billing.plans import PLANS
from utils.billing import get_clinic_usage_status
from dotenv import load_dotenv

from database import db, User, Voicemail, Clinic, TriageCard
from flask_migrate import Migrate
from services.storage_service import upload_file

# ------------------------
# LOAD ENV
# ------------------------

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# ------------------------
# APP SETUP
# ------------------------

app = Flask(__name__)

print("🔥🔥🔥 THIS IS THE REAL RUN.PY 🔥🔥🔥")
print("APP OBJECT ID:", id(app))  # <-- Debug print after app is created

app.secret_key = os.getenv("SECRET_KEY")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

app.config["ENABLE_AI_EXTRACTION"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ------------------------
# 🔥 LOGIN MANAGER
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

db.init_app(app)
migrate = Migrate(app, db)

# ------------------------
# ✅ TEMP ADMIN ROUTE (MOVED HERE)
# ------------------------

@app.route("/create-admin")
def create_admin():
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

# ❌ TEMPORARILY DISABLED TO DEBUG 500 ERROR
# from app.routes.ingestion import ingestion_bp
# app.register_blueprint(ingestion_bp)

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

# ✅ TEMP DEBUG ROUTE ADDED (ONLY CHANGE MADE)
@app.route("/debug-clinics")
def debug_clinics():
    from database import Clinic
    clinics = Clinic.query.all()
    return {c.id: c.ingest_email_token for c in clinics}

@app.route("/seed-clinic")
def seed_clinic():
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

# ------------------------
# UPLOAD ROUTE (FIXED FILENAME)
# ------------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload_voicemail():
    file = request.files.get("file")
    
    if not file:
        return jsonify({"error": "No file provided"}), 400

    # ✅ ALWAYS generate a safe filename (ignore client filename)
    ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
    filename = f"{uuid.uuid4()}{ext}"

    # Upload to storage
    s3_key = upload_file(file, filename=filename)  # make sure your upload_file supports custom filename

    voicemail = Voicemail(
        clinic_id=current_user.clinic_id,
        filename=filename,        # guaranteed non-None
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

# ------------------------
# STEP 8 — FLASK WEBHOOK ENDPOINT (WORKING)
# ------------------------

import boto3

# Initialize S3 client (make sure AWS credentials are in your environment)
s3 = boto3.client("s3")

@app.route("/webhooks/email-ingest", methods=["POST"], strict_slashes=False)
def email_ingest():
    try:
        # 1️⃣ Get recipient and file from request
        recipient = request.form.get("recipient")
        file = request.files.get("file")

        if not recipient or not file:
            return jsonify({"error": "Missing recipient or file"}), 400

        # 2️⃣ Extract clinic token from recipient email
        token = recipient.split("@")[0]

        clinic = Clinic.query.filter_by(ingest_email_token=token).first()
        if not clinic:
            return jsonify({"error": "Invalid clinic token"}), 404

        # 3️⃣ Prepare filename and upload to S3
        ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
        filename = f"voicemails/{uuid.uuid4()}{ext}"
        s3.upload_fileobj(file, "voicecarepro-audio-prod", filename)

        # 4️⃣ Create Voicemail DB record (guaranteed filename)
        voicemail = Voicemail(
            clinic_id=clinic.id,
            filename=file.filename if file.filename else f"voicemail_{uuid.uuid4()}.mp3",
            audio_url=filename,
            source="email_ingest",
            received_at=datetime.utcnow(),
            status="pending"
        )

        db.session.add(voicemail)
        db.session.commit()

        return jsonify({"success": True, "voicemail_id": voicemail.id}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

print("===== REGISTERED ROUTES =====")
for rule in app.url_map.iter_rules():
    print(rule)
print("=============================")