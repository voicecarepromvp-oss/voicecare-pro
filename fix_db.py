import sqlite3

print("🚀 Running database patch...")

conn = sqlite3.connect("instance/voicemail_system.db")
cursor = conn.cursor()

cursor.execute("ALTER TABLE voicemails ADD COLUMN matched_keywords TEXT;")

conn.commit()
conn.close()

print("✅ matched_keywords column added successfully")
