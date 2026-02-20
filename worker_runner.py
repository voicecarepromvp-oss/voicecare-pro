from run import app
from workers.transcription_worker import worker_loop

if __name__ == "__main__":
    with app.app_context():
        print("🔥 Transcription worker started...")
        worker_loop()
