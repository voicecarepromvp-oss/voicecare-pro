from dotenv import load_dotenv
import os

load_dotenv()

from utils.ai_processor import VoicemailAIProcessor

print("DEEPGRAM:", os.getenv("DEEPGRAM_API_KEY"))
print("OPENAI:", os.getenv("OPENAI_API_KEY"))

processor = VoicemailAIProcessor()

print("Processor initialized successfully")

result1 = processor.extract_patient_info(
    "Patient John Doe has chest pain for 2 days."
)

print("Extraction result:", result1)

result2 = processor.summarize_and_triage(
    "Patient John Doe has chest pain for 2 days.",
    {}
)

print("Summary result:", result2)