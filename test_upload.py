import requests

url = "http://127.0.0.1:5000/upload"

files = {
    "file": open("test.mp3", "rb")
}

data = {
    "clinic_id": 1
}

r = requests.post(url, files=files, data=data)

print("Status:", r.status_code)
print("Response:", r.text)
