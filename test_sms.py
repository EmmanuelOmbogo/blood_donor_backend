from sms_service import send_sms

try:
    response = send_sms(
        "+254713294911",
        "Welcome to Damulink Blood Donor System! SMS test."
    )
    print("SMS request response:", response)

except Exception as error:
    print("SMS failed:", error)