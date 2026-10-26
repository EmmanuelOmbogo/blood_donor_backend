import os
import africastalking

def send_sms(phone_number, message):
    username = os.environ.get("AT_USERNAME", "sandbox")
    api_key = os.environ.get("AT_API_KEY")

    if not api_key:
        raise ValueError("Africa's Talking API key is missing.")

    africastalking.initialize(username, api_key)
    sms = africastalking.SMS

    return sms.send(message, [phone_number])