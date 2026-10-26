import re
import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

def normalize_phone_number(phone: str) -> str:
    """
    Normalizes a phone number to standard E.164 format for Kenya (+254...)
    or international standard.
    Examples:
      0712345678 -> +254712345678
      0112345678 -> +254112345678
      254712345678 -> +254712345678
      +254 712 345 678 -> +254712345678
    """
    if not phone:
        return ""
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r'[\s\-\(\)]', '', phone.strip())

    if cleaned.startswith('+'):
        return cleaned
    elif cleaned.startswith('0'):
        # Local Kenyan format: 07... or 01...
        return '+254' + cleaned[1:]
    elif cleaned.startswith('254'):
        return '+' + cleaned
    elif len(cleaned) == 9 and (cleaned.startswith('7') or cleaned.startswith('1')):
        return '+254' + cleaned
    else:
        # Default prefix + if missing
        return '+' + cleaned

def get_africastalking_config():
    try:
        from dotenv import load_dotenv
        import os
        env_path = getattr(settings, 'BASE_DIR', None)
        if env_path:
            load_dotenv(env_path / '.env', override=True)
    except Exception:
        pass

    username = os.getenv('AT_USERNAME') or getattr(settings, 'AT_USERNAME', 'sandbox')
    api_key = os.getenv('AT_API_KEY') or getattr(settings, 'AT_API_KEY', '')
    sender_id = os.getenv('AT_SENDER_ID') or getattr(settings, 'AT_SENDER_ID', '')
    env = os.getenv('AT_ENV') or getattr(settings, 'AT_ENV', 'sandbox' if username.lower() == 'sandbox' else 'production')

    return {
        'username': username.strip(),
        'api_key': api_key.strip(),
        'sender_id': sender_id.strip(),
        'env': env.strip().lower()
    }

def send_sms(to_phone: str, message: str) -> dict:
    """
    Sends an SMS using Africa's Talking REST API (Live or Sandbox).
    Returns a dict with:
      success: bool
      status: 'delivered' | 'sent' | 'failed'
      response: dict or raw response
      error: str (if any)
    """
    config = get_africastalking_config()
    normalized = normalize_phone_number(to_phone)

    if not normalized:
        return {"success": False, "status": "failed", "error": "Invalid phone number"}

    if not config['api_key'] or config['api_key'] == 'your_africastalking_api_key_here':
        logger.warning(
            f"[SMS MOCK/UNCONFIGURED] Would send to {normalized}: {message} "
            f"(AT_API_KEY is not configured in .env)"
        )
        return {
            "success": False,
            "status": "failed",
            "error": "AT_API_KEY not configured in backend .env. Please configure AT_USERNAME and AT_API_KEY."
        }

    # Africa's Talking API endpoint
    if config['env'] == 'sandbox' or config['username'].lower() == 'sandbox':
        url = 'https://api.sandbox.africastalking.com/version1/messaging'
    else:
        url = 'https://api.africastalking.com/version1/messaging'

    headers = {
        'apiKey': config['api_key'],
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    payload = {
        'username': config['username'],
        'to': normalized,
        'message': message,
    }

    if config['sender_id']:
        payload['from'] = config['sender_id']

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        logger.info(f"Africa's Talking response [{response.status_code}]: {response.text}")

        try:
            res_json = response.json()
        except Exception:
            res_json = {"raw": response.text}

        if response.status_code in [200, 201]:
            # Inspect Africa's Talking response structure
            recipients = res_json.get('SMSMessageData', {}).get('Recipients', [])
            if recipients:
                first_recipient = recipients[0]
                status_code = first_recipient.get('statusCode')
                status_text = first_recipient.get('status', '').lower()

                # Status codes: 100 (Processed), 101 (Sent), 102 (Queued)
                if status_code in [100, 101, 102] or 'success' in status_text or 'sent' in status_text:
                    return {
                        "success": True,
                        "status": "delivered" if 'success' in status_text else "sent",
                        "response": res_json,
                        "messageId": first_recipient.get('messageId')
                    }
                else:
                    return {
                        "success": False,
                        "status": "failed",
                        "error": f"Recipient status: {first_recipient.get('status')} (Code: {status_code})",
                        "response": res_json
                    }

            return {
                "success": True,
                "status": "sent",
                "response": res_json
            }
        else:
            return {
                "success": False,
                "status": "failed",
                "error": f"HTTP {response.status_code}: {response.text}",
                "response": res_json
            }

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to Africa's Talking: {e}")
        return {
            "success": False,
            "status": "failed",
            "error": f"Connection error: {str(e)}"
        }

def send_blood_alert_to_match(match) -> dict:
    """
    Composes and sends an emergency SMS alert to a matched donor for a blood request.
    """
    donor = match.donor
    req = match.request

    if not donor.phone_number:
        match.sms_status = 'failed'
        match.save(update_fields=['sms_status'])
        return {"success": False, "error": "Donor has no phone number"}

    if donor.opted_out or not donor.consent_to_sms:
        match.sms_status = 'failed'
        match.save(update_fields=['sms_status'])
        return {"success": False, "error": "Donor has opted out or withdrawn SMS consent"}

    message = (
        f"EMERGENCY BLOOD ALERT: {req.hospital_name} ({req.area}) urgently needs "
        f"{req.units_needed} unit(s) of {req.blood_group} blood. "
        f"You are a compatible donor! "
        f"Reply YES to donate, NO if unavailable, or STOP to opt-out. Ref: {req.reference}"
    )

    result = send_sms(donor.phone_number, message)
    match.sms_status = result['status']
    match.save(update_fields=['sms_status'])

    return result

def handle_incoming_sms(from_phone: str, text: str) -> dict:
    """
    Handles an incoming SMS reply from Africa's Talking callback webhook.
    Processes 'YES', 'NO', 'STOP' case-insensitively.
    """
    from .models import Donor, MatchedDonor

    normalized_from = normalize_phone_number(from_phone)
    clean_text = text.strip().upper()

    # Find donor by normalized phone
    donors = list(Donor.objects.all())
    matching_donor = None
    for d in donors:
        if normalize_phone_number(d.phone_number) == normalized_from:
            matching_donor = d
            break

    if not matching_donor:
        return {"status": "ignored", "message": f"No registered donor found for {from_phone}"}

    now = timezone.now()

    if clean_text == 'STOP':
        matching_donor.opted_out = True
        matching_donor.consent_to_sms = False
        matching_donor.save(update_fields=['opted_out', 'consent_to_sms'])

        # Update any pending matches
        MatchedDonor.objects.filter(donor=matching_donor, response='pending').update(
            response='opted_out',
            responded_at=now
        )
        return {"status": "opted_out", "donor": matching_donor.full_name}

    elif clean_text in ['YES', 'Y']:
        # Update latest pending match
        latest_match = MatchedDonor.objects.filter(donor=matching_donor, response='pending').order_by('-request__created_at').first()
        if latest_match:
            latest_match.response = 'yes'
            latest_match.responded_at = now
            latest_match.save(update_fields=['response', 'responded_at'])
            return {"status": "confirmed_yes", "donor": matching_donor.full_name, "request": latest_match.request.reference}
        return {"status": "no_pending_match", "donor": matching_donor.full_name}

    elif clean_text in ['NO', 'N']:
        latest_match = MatchedDonor.objects.filter(donor=matching_donor, response='pending').order_by('-request__created_at').first()
        if latest_match:
            latest_match.response = 'no'
            latest_match.responded_at = now
            latest_match.save(update_fields=['response', 'responded_at'])
            return {"status": "declined_no", "donor": matching_donor.full_name, "request": latest_match.request.reference}
        return {"status": "no_pending_match", "donor": matching_donor.full_name}

    return {"status": "unrecognized_reply", "text": text}
