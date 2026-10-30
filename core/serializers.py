from .models import User, Donor, BloodRequest, MatchedDonor, DonationDrive

COMPATIBLE_DONORS_FOR_RECIPIENT = {
    'O-': ['O-'],
    'O+': ['O-', 'O+'],
    'A-': ['O-', 'A-'],
    'A+': ['O-', 'O+', 'A-', 'A+'],
    'B-': ['O-', 'B-'],
    'B+': ['O-', 'O+', 'B-', 'B+'],
    'AB-': ['O-', 'A-', 'B-', 'AB-'],
    'AB+': ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'],
}

def mask_phone_number(phone):
    if not phone:
        return ""
    clean = phone.strip()
    if len(clean) <= 6:
        return clean[:2] + "****"
    # Show first 7 and last 3 digits, masking middle with ** ***
    prefix = clean[:7]
    suffix = clean[-3:]
    return f"{prefix}***{suffix}"

def serialize_user(user):
    return {
        "id": str(user.id),
        "name": user.name or user.email.split('@')[0],
        "email": user.email,
        "role": user.role,
        "organization": user.organization,
    }

def serialize_donor(donor):
    return {
        "id": str(donor.id),
        "fullName": donor.full_name,
        "phoneNumber": donor.phone_number,
        "nationalId": donor.national_id,
        "location": donor.location,
        "bloodGroup": donor.blood_group,
        "lastDonationDate": donor.last_donation_date.isoformat() if donor.last_donation_date else None,
        "eligible": donor.eligible,
        "consentToSms": donor.consent_to_sms,
        "optedOut": donor.opted_out,
        "screeningStatus": donor.screening_status,
        "createdAt": donor.created_at.isoformat() if donor.created_at else None,
    }

def serialize_matched_donor(match):
    return {
        "donorId": str(match.donor.id),
        "fullName": match.donor.full_name,
        "phoneNumberMasked": mask_phone_number(match.donor.phone_number),
        "location": match.donor.location,
        "bloodGroup": match.donor.blood_group,
        "response": match.response,
        "smsStatus": match.sms_status,
        "respondedAt": match.responded_at.isoformat() if match.responded_at else None,
    }

def serialize_request_candidate(donor):
    """Return the contact fields staff need to populate a new request."""
    return {
        "id": str(donor.id),
        "fullName": donor.full_name,
        "phoneNumber": donor.phone_number,
        "location": donor.location,
        "bloodGroup": donor.blood_group,
    }

def serialize_blood_request(req):
    matches = [serialize_matched_donor(m) for m in req.matched_donors.select_related('donor').all()]
    return {
        "id": str(req.id),
        "reference": req.reference,
        "hospitalName": req.hospital_name,
        "contactName": req.contact_name,
        "contactPhone": req.contact_phone,
        "bloodGroup": req.blood_group,
        "unitsNeeded": req.units_needed,
        "unitsFulfilled": req.units_fulfilled,
        "area": req.area,
        "urgency": req.urgency,
        "neededBy": req.needed_by.isoformat() if req.needed_by else None,
        "notes": req.notes,
        "status": req.status,
        "matchedDonors": matches,
        "smsDispatchedAt": req.sms_dispatched_at.isoformat() if req.sms_dispatched_at else None,
        "createdAt": req.created_at.isoformat() if req.created_at else None,
    }

def serialize_donation_drive(drive):
    return {
        "id": str(drive.id),
        "name": drive.name,
        "venue": drive.venue,
        "area": drive.area,
        "startsAt": drive.starts_at.isoformat() if drive.starts_at else None,
        "endsAt": drive.ends_at.isoformat() if drive.ends_at else None,
        "status": drive.status,
        "registeredDonors": drive.registered_donors,
    }
