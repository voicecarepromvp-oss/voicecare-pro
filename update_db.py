from app import app, db, Voicemail
from sqlalchemy import text  # 👈 import this

def update_database():
    with app.app_context():
        with db.engine.connect() as connection:
            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN transcription TEXT;'))
            except Exception as e:
                print("Column transcription may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN summary TEXT;'))
            except Exception as e:
                print("Column summary may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN category VARCHAR(100);'))
            except Exception as e:
                print("Column category may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN patient_name VARCHAR(255);'))
            except Exception as e:
                print("Column patient_name may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN phone_number VARCHAR(20);'))
            except Exception as e:
                print("Column phone_number may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN processed BOOLEAN DEFAULT 0;'))
            except Exception as e:
                print("Column processed may already exist:", e)

            try:
                connection.execute(text('ALTER TABLE voicemail ADD COLUMN urgency_score INTEGER DEFAULT 5;'))
            except Exception as e:
                print("Column urgency_score may already exist:", e)

        print("✅ Database update complete.")

if __name__ == "__main__":
    update_database()
