# check_env.py
import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

print("Project root:", BASE_DIR)
print("OPENAI key present?", bool(os.getenv("OPENAI_API_KEY")))
