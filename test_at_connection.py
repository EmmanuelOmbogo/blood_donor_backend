import os
import requests

url = "https://api.sandbox.africastalking.com/version1/messaging"

headers = {
    "apiKey": os.environ["AT_API_KEY"],
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

data = {
    "username": "sandbox",
    "to": "+254713294911",
    "message": "Connection test",
}

try:
    response = requests.post(url, headers=headers, data=data, timeout=15)
    print("HTTP status:", response.status_code)
    print("Response:", response.text[:500])
except requests.exceptions.RequestException as error:
    print("Connection error:", error)
