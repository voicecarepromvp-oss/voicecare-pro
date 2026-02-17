import sqlite3

conn = sqlite3.connect("instance/voicemail_system.db")
cursor = conn.cursor()

print("\n--- STORED VOICEMAIL RECORDS ---\n")

rows = cursor.execute("SELECT id, filename, intent, department, priority, confidence FROM voicemails").fetchall()

if not rows:
    print("No records found yet.")
else:
    for row in rows:
        print(row)

conn.close()
