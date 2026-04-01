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
    jsonify,
    abort
)

from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user
)

from services.billing_service import BillingService
from apscheduler.schedulers.background import BackgroundScheduler
from services.digest_service import send_daily_digest
from billing.plans import PLANS
from utils.billing import get_clinic_usage_status
from dotenv import load_dotenv

from database import db, User, Voicemail, Clinic, TriageCard
from flask_migrate import Migrate
from services.storage_service import upload_file, generate_presigned_url

# ------------------------
# LOAD ENV
# ------------------------

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

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
    if os.getenv("ENV") != "dev":
        abort(403)

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
# 🆕 WEEKLY ANALYTICS HELPER
# ------------------------

def get_weekly_analytics(clinic_id):

    one_week_ago = datetime.utcnow() - timedelta(days=7)

    voicemails = Voicemail.query.filter(
        Voicemail.clinic_id == clinic_id,
        Voicemail.received_at >= one_week_ago
    ).all()

    total = len(voicemails)

    high = len([v for v in voicemails if v.urgency_level == "high"])
    medium = len([v for v in voicemails if v.urgency_level == "medium"])
    low = len([v for v in voicemails if v.urgency_level == "low"])

    # Most common triage category
    categories = {}
    for v in voicemails:
        if v.triage_category:
            categories[v.triage_category] = categories.get(v.triage_category, 0) + 1

    most_common = max(categories, key=categories.get) if categories else "N/A"

    # Estimated time saved (4 minutes per voicemail)
    minutes_saved = total * 4
    hours_saved = round(minutes_saved / 60, 2)

    return {
        "total": total,
        "high": high,
        "medium": medium,
        "low": low,
        "most_common": most_common,
        "hours_saved": hours_saved
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
    return render_template("landing.html")

@app.route("/seed-clinic")
def seed_clinic():
    if os.getenv("ENV") != "dev":
        abort(403)

    existing = Clinic.query.first()
    if existing:
        return {"message": "Clinic already exists", "clinic_id": existing.id}
    
# ------------------------
# SIGNUP ROUTE (STEP 1)
# ------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
       return redirect(url_for("dashboard"))

    from werkzeug.security import generate_password_hash

    if request.method == "POST":
        clinic_name = request.form.get("clinic_name")
        email = request.form.get("email")
        password = request.form.get("password")

        if not clinic_name or not email or not password:
            flash("All fields are required", "error")
            return render_template("signup.html")

        # 1️⃣ Create Clinic with unique ingestion token
        token = secrets.token_hex(16)
        clinic = Clinic(
            name=clinic_name,
            email=email,
            ingest_email_token=token,
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

        # 2️⃣ Create Admin User
        user = User(
            email=email,
            clinic_id=clinic.id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # 3️⃣ Log in the user
        login_user(user)

        flash("Account created successfully!", "success")
        return redirect(url_for("dashboard"))

    # GET request
    return render_template("signup.html")    

# 🆕 MANUAL CLINIC PROVISIONING (FOR REAL ONBOARDING)
@app.route("/provision-clinic")
def provision_clinic():
    if os.getenv("ENV") != "dev":
        abort(403)

    name = request.args.get("name")
    email = request.args.get("email")
    token = request.args.get("token")

    if not name or not email or not token:
        return {"error": "Missing required params"}, 400

    existing = Clinic.query.filter_by(ingest_email_token=token).first()
    if existing:
        return {"error": "Token already exists"}, 400

    clinic = Clinic(
        name=name,
        email=email,
        ingest_email_token=token,
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

    return {
        "message": "Clinic created",
        "clinic_id": clinic.id,
        "ingest_address": f"{token}@mail.getvoicecarepro.com"
    }

# ------------------------
# USER CREATION ROUTE
# ------------------------
@app.route("/create-user")
def create_user():
    if os.getenv("ENV") != "dev":
        abort(403)
        
    email = request.args.get("email")
    password = request.args.get("password")
    clinic_id = request.args.get("clinic_id")

    if not email or not password or not clinic_id:
        return {"error": "Missing params"}, 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return {"error": "User already exists"}, 400

    user = User(
        email=email,
        clinic_id=int(clinic_id)
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return {"message": "User created"}

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
       return redirect(url_for("dashboard"))
    
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

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/hipaa")
def hipaa():
    return render_template("hipaa.html")

# ------------------------
# UPLOAD ROUTE (FIXED FILENAME)
# ------------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload_voicemail():
    file = request.files.get("file")
    
    if not file:
        return jsonify({"error": "No file provided"}), 400

    # ----------------------------
    # 🔥 BILLING CHECK (ADD THIS HERE)
    # ----------------------------
    clinic = current_user.clinic

    allowed, error = BillingService.can_process_voicemail(clinic)

    if not allowed:
        return jsonify({"error": error}), 403

    # ----------------------------
    # FILE PROCESSING STARTS HERE
    # ----------------------------

    # ALWAYS generate a safe filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ".mp3"
    filename = f"{uuid.uuid4()}{ext}"

    # Upload to storage
    s3_key = upload_file(file, filename)

    voicemail = Voicemail(
        clinic_id=current_user.clinic_id,
        filename=filename,
        audio_url=s3_key,
        source="clinic_upload",
        received_at=datetime.utcnow(),
        status="received"
    )

    db.session.add(voicemail)
    db.session.commit()

    # ----------------------------
    # 🔥 RECORD USAGE (ADD THIS HERE)
    # ----------------------------

    BillingService.record_usage(clinic)
    db.session.commit()

    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@login_required
def dashboard():

    department = request.args.get("department")

    query = Voicemail.query.filter_by(clinic_id=current_user.clinic_id)

    if department:
        query = query.filter(Voicemail.department.ilike(f"%{department}%"))

    voicemails = query.order_by(Voicemail.id.desc()).all()

    clinic = current_user.clinic
    usage = get_clinic_usage(clinic)
    usage_status = get_clinic_usage_status(clinic)

    analytics = get_weekly_analytics(current_user.clinic_id)

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

    auto_routed = Voicemail.query.filter(
        Voicemail.clinic_id == current_user.clinic_id
    ).count()

    department_counts = {
    "urgent": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="urgent"
    ).count(),

    "nurse": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="nurse"
    ).count(),

    "scheduling": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="scheduling"
    ).count(),

    "provider": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="provider"
    ).count(),

    "front_desk": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="front_desk"
    ).count(),

    "general": Voicemail.query.filter_by(
        clinic_id=current_user.clinic_id,
        department="general"
    ).count(),
}

    return render_template(
        "dashboard.html",
        clinic=clinic,
        voicemails=voicemails,
        usage=usage,
        usage_status=usage_status,
        total_voicemails=total_voicemails,
        pending_processing=pending_processing,
        processed_today=processed_today,
        auto_routed=auto_routed,
        analytics=analytics,
        department_counts=department_counts
    )

# -----------------------------
# Voicemail Detail Page
# -----------------------------

@app.route("/voicemail/<int:voicemail_id>", methods=["GET", "POST"])
@login_required
def voicemail_detail(voicemail_id):

    voicemail = Voicemail.query.filter_by(
        id=voicemail_id,
        clinic_id=current_user.clinic_id
    ).first_or_404()

    if request.method == "POST":

        voicemail.intent = request.form.get("intent")
        voicemail.department = request.form.get("department")

        reviewed = request.form.get("reviewed")
        voicemail.needs_review = 0 if reviewed else 1

        db.session.commit()

        flash("Voicemail updated successfully", "success")
        return redirect(url_for("dashboard"))

    # 🔊 Generate secure audio URL
    audio_url = None
    if voicemail.audio_url:
        audio_url = generate_presigned_url(voicemail.audio_url)

    return render_template(
        "voicemail_detail.html",
        voicemail=voicemail,
        audio_url=audio_url
    )

# ------------------------
# STEP 8 — FLASK WEBHOOK ENDPOINT (WORKING)
# ------------------------

# ------------------------
# STEP 8 — FLASK WEBHOOK ENDPOINT (UPDATED JSON VERSION)
# ------------------------

import boto3
import email
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import re
import uuid
from datetime import datetime

@app.route("/webhooks/email-ingest", methods=["POST"], strict_slashes=False)
def email_ingest():
    try:
        s3 = boto3.client("s3")

        # 🔥 FORCE JSON PARSING (CRITICAL FIX)
        try:
           data = request.get_json(force=True)
        except Exception:
           logger.error(f"Failed to parse JSON. Raw data: {request.data}")
           return jsonify({"error": "Invalid JSON"}), 400

        logger.info(f"PARSED JSON: {data}")

        bucket = data.get("bucket")
        key = data.get("key")
        logger.info(f"Webhook received - Bucket: {bucket}, Key: {key}")

        if not bucket or not key:
            logger.error(f"Missing S3 data - bucket: {bucket}, key: {key}")
            return jsonify({"error": "Missing S3 data"}), 400

        # 1️⃣ Download raw email from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        raw_email = response["Body"].read()

        # 2️⃣ Parse MIME
        msg = BytesParser(policy=policy.default).parsebytes(raw_email)

        # 🔍 DEBUG LOGGING
        logger.info(f"EMAIL FROM HEADER: {msg.get('From')}")
        logger.info(f"EMAIL SUBJECT: {msg.get('Subject')}")
        logger.info(f"EMAIL TO: {msg.get('To')}")
        logger.info(f"EMAIL HEADERS: {list(msg.items())}")

        # 2.5️⃣ Extract caller phone from email metadata

        def extract_phone(text):
            match = re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text or "")
            return match.group(0) if match else None

        caller_phone = None

        # 1️⃣ Subject
        caller_phone = extract_phone(msg.get("Subject", ""))

        # 2️⃣ From
        if not caller_phone:
           caller_phone = extract_phone(msg.get("From", ""))

        # 3️⃣ 🔥 Check ALL HEADERS (CRITICAL FIX)
        if not caller_phone:
          for key, value in msg.items():
            if value:
                caller_phone = extract_phone(str(value))
                if caller_phone:
                   logger.info(f"Caller phone found in header {key}: {caller_phone}")
                   break

        # 4️⃣ 🔥 Check EMAIL BODY (LAST RESORT)
        if not caller_phone:
           try:
                body = msg.get_body(preferencelist=('plain', 'html'))
                if body:
                  content = body.get_content()
                  caller_phone = extract_phone(content)
           except Exception as e:
               logger.error(f"Error extracting from body: {e}")

        logger.info(f"📞 FINAL Caller phone detected: {caller_phone}")

        # 3️⃣ Extract recipient + token
        from email.utils import getaddresses

        recipients = getaddresses([msg.get("To", "")])

        token = None

        for name, addr in recipients:
            if addr.endswith("@mail.getvoicecarepro.com"):
                token = addr.split("@")[0]
                break

        if not token:
           logger.error(f"No valid ingest email found in TO: {recipients}")
           return jsonify({"error": "No valid clinic email found"}), 400

        clinic = Clinic.query.filter_by(ingest_email_token=token).first()
        if not clinic:
            return jsonify({"error": "Invalid clinic token"}), 404

        # 4️⃣ Extract audio attachment
        audio_file = None
        audio_filename = None

        for part in msg.iter_attachments():
            if part.get_content_type().startswith("audio/"):
                audio_file = part.get_content()
                audio_filename = part.get_filename()
                break

        if not audio_file:
            return jsonify({"error": "No audio attachment found"}), 400

        # 5️⃣ Save audio to S3 (voicemails folder)
        ext = audio_filename.split(".")[-1] if audio_filename else "mp3"
        filename = f"voicemails/{uuid.uuid4()}.{ext}"

        s3.put_object(
            Bucket="voicecarepro-audio-prod",
            Key=filename,
            Body=audio_file
        )

        # 6️⃣ Create voicemail record
        voicemail = Voicemail(
            clinic_id=clinic.id,
            filename=audio_filename,
            audio_url=filename,
            source="email_ingest",
            received_at=datetime.utcnow(),
            status="pending",
            s3_key=key
        )

        # 🔥 Force assign AFTER creation
        voicemail.caller_phone = caller_phone

        logger.info(f"💾 SAVING caller_phone to DB: {caller_phone}")

        db.session.add(voicemail)
        db.session.commit()

        logger.info(f"✅ DB STORED caller_phone: {voicemail.caller_phone}")

        return jsonify({"success": True, "voicemail_id": voicemail.id}), 200
    
    except Exception as e:
        logger.error(f"❌ Email ingest failed: {e}")
        return jsonify({"error": str(e)}), 500
    
# ------------------------
# DEBUG TOKEN ROUTE
# ------------------------

@app.route("/debug/token")
def debug_token():
    return {"status": "route works"}

@app.route("/debug/all-voicemails")
def debug_all_voicemails():
    vms = Voicemail.query.order_by(Voicemail.id.desc()).all()
    return {
        "voicemails": [
            {
                "id": v.id,
                "clinic_id": v.clinic_id,
                "status": v.status,
                "caller_phone": v.caller_phone,
                "patient_phone": v.patient_phone
            } for v in vms
        ]
    }

@app.route("/debug/clinic-email")
def debug_clinic_email():
    clinic = Clinic.query.first()
    if not clinic:
        return {"error": "No clinic found"}

    return {
        "clinic_id": clinic.id,
        "clinic_name": clinic.name,
        "clinic_email": clinic.email
    }

@app.route("/debug/all-clinics")
def debug_all_clinics():
    from database import Clinic
    clinics = Clinic.query.all()
    return {
        "clinics": [
            {
                "id": c.id,
                "name": c.name,
                "token": c.ingest_email_token,
                "email": c.email
            }
            for c in clinics
        ]
    }

# ------------------------
# SERVER START (RENDER FIX)
# ------------------------

if __name__ == "__main__":
    print("🔥🔥🔥 THIS IS THE REAL RUN.PY 🔥🔥🔥")
    print("APP OBJECT ID:", id(app))

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)