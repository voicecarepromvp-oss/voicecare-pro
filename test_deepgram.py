import requests

API_KEY = "46767894b538816a5b34e737fc1a6cb546b996d9"
AUDIO_FILE = "test.mp3"

url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"

headers = {
    "Authorization": f"Token {API_KEY}",
    "Content-Type": "audio/mpeg"
}

with open(AUDIO_FILE, "rb") as audio:
    response = requests.post(url, headers=headers, data=audio)

print(response.status_code)
print(response.json())
