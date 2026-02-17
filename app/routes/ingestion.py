print("🔥 ingestion.py LOADED")

from flask import Blueprint

ingestion_bp = Blueprint("ingestion", __name__, url_prefix="/ingest")


@ingestion_bp.route("/voicemail", methods=["POST"])
def ingest_voicemail():
    print("🔥 INGESTION ENDPOINT HIT")
    return "OK", 200
