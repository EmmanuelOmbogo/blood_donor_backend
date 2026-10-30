import json
import random
from datetime import datetime, timezone as dt_timezone
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.contrib.auth import authenticate
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import User, AuthToken, Donor, BloodRequest, MatchedDonor, DonationDrive
from .authentication import BearerAuthentication
from .serializers import (
    COMPATIBLE_DONORS_FOR_RECIPIENT,
    serialize_user,
    serialize_donor,
    serialize_matched_donor,
    serialize_request_candidate,
    serialize_blood_request,
    serialize_donation_drive,
)
from .sms_service import (
    send_sms,
    send_blood_alert_to_match,
    handle_incoming_sms,
    normalize_phone_number,
)

@api_view(['POST'])
@permission_classes([AllowAny])
def auth_login(request):
    email = (request.data.get('email') or '').strip().lower()
    password = request.data.get('password') or ''

    if not email or not password:
        return Response(
            {"message": "Email and password are required.", "fieldErrors": {}},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = authenticate(request, username=email, password=password)
    if not user:
        # Also check by email directly if username differs
        try:
            u = User.objects.get(email=email)
            if u.check_password(password):
                user = u
        except User.DoesNotExist:
            pass

    if not user:
        return Response(
            {"message": "Invalid email or password.", "fieldErrors": {"password": "Incorrect password"}},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Invalidate old tokens or create new
    token = AuthToken.generate_token(user)
    return Response({
        "access": token.key,
        "user": serialize_user(user)
    })

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
@permission_classes([IsAuthenticated])
def auth_me(request):
    return Response(serialize_user(request.user))

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def dashboard_summary(request):
    total_donors = Donor.objects.count()
    eligible_donors = Donor.objects.filter(eligible=True, opted_out=False).count()
    active_requests = BloodRequest.objects.filter(status__in=['open', 'notified', 'partially_fulfilled']).count()
    fulfilled_sum = BloodRequest.objects.aggregate(total=Sum('units_fulfilled'))['total'] or 0

    blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    group_counts = {g: 0 for g in blood_groups}
    for item in Donor.objects.values('blood_group').annotate(count=Count('blood_group')):
        bg = item['blood_group']
        if bg in group_counts:
            group_counts[bg] = item['count']

    recent_qs = BloodRequest.objects.order_by('-created_at')[:5]
    recent_requests = [serialize_blood_request(req) for req in recent_qs]

    return Response({
        "registeredDonors": total_donors,
        "eligibleDonors": eligible_donors,
        "activeRequests": active_requests,
        "livesSupported": fulfilled_sum,
        "donorsByBloodGroup": group_counts,
        "recentRequests": recent_requests
    })

@api_view(['GET', 'POST'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def donors_list_or_create(request):
    if request.method == 'GET':
        search = (request.query_params.get('search') or '').strip()
        blood_group = (request.query_params.get('bloodGroup') or '').strip()
        area = (request.query_params.get('area') or '').strip()

        qs = Donor.objects.order_by('-created_at')
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(national_id__icontains=search) |
                Q(location__icontains=search)
            )
        if blood_group:
            qs = qs.filter(blood_group=blood_group)
        if area:
            qs = qs.filter(location__icontains=area)

        results = [serialize_donor(d) for d in qs]
        return Response({
            "results": results,
            "count": len(results),
            "next": None,
            "previous": None
        })

    # POST create donor
    data = request.data
    full_name = (data.get('fullName') or '').strip()
    phone_number = (data.get('phoneNumber') or '').strip()
    national_id = (data.get('nationalId') or '').strip()
    location = (data.get('location') or '').strip()
    blood_group = (data.get('bloodGroup') or '').strip()
    last_donation = data.get('lastDonationDate')
    consent_to_sms = bool(data.get('consentToSms'))

    field_errors = {}
    if not full_name:
        field_errors['fullName'] = 'Full name is required.'
    if not phone_number:
        field_errors['phoneNumber'] = 'Phone number is required.'
    if not national_id:
        field_errors['nationalId'] = 'National ID is required.'
    if not location:
        field_errors['location'] = 'Location is required.'
    if not blood_group:
        field_errors['bloodGroup'] = 'Blood group is required.'

    if field_errors:
        return Response(
            {"message": "Please correct the errors below.", "fieldErrors": field_errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    last_donation_dt = None
    if last_donation:
        try:
            if isinstance(last_donation, str):
                last_donation_dt = datetime.fromisoformat(last_donation.replace('Z', '+00:00'))
        except Exception:
            pass

    donor = Donor.objects.create(
        full_name=full_name,
        phone_number=phone_number,
        national_id=national_id,
        location=location,
        blood_group=blood_group,
        last_donation_date=last_donation_dt,
        consent_to_sms=consent_to_sms,
        eligible=True,
        opted_out=False,
        screening_status='clear'
    )

    return Response(serialize_donor(donor), status=status.HTTP_201_CREATED)

@api_view(['GET', 'POST'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def requests_list_or_create(request):
    if request.method == 'GET':
        blood_group = (request.query_params.get('bloodGroup') or '').strip()
        area = (request.query_params.get('area') or '').strip()
        if blood_group:
            compatible_groups = COMPATIBLE_DONORS_FOR_RECIPIENT.get(blood_group, [])
            donors = Donor.objects.filter(
                blood_group__in=compatible_groups,
                eligible=True,
                consent_to_sms=True,
                opted_out=False,
                screening_status='clear',
            ).order_by('created_at')
            candidates = list(donors)
            if area:
                candidates.sort(key=lambda d: (0 if area.lower() in d.location.lower() or d.location.lower() in area.lower() else 1, d.created_at))
            return Response({"results": [serialize_request_candidate(d) for d in candidates[:20]], "count": len(candidates)})
        search = (request.query_params.get('search') or '').strip()
        status_filter = (request.query_params.get('status') or '').strip()

        qs = BloodRequest.objects.order_by('-created_at')
        if search:
            qs = qs.filter(
                Q(reference__icontains=search) |
                Q(hospital_name__icontains=search) |
                Q(contact_name__icontains=search) |
                Q(area__icontains=search)
            )
        if status_filter:
            qs = qs.filter(status=status_filter)

        results = [serialize_blood_request(req) for req in qs]
        return Response({
            "results": results,
            "count": len(results),
            "next": None,
            "previous": None
        })

    # POST create request
    data = request.data
    hospital_name = (data.get('hospitalName') or '').strip()
    contact_name = (data.get('contactName') or '').strip()
    contact_phone = (data.get('contactPhone') or '').strip()
    blood_group = (data.get('bloodGroup') or '').strip()
    try:
        units_needed = int(data.get('unitsNeeded') or 1)
    except (TypeError, ValueError):
        units_needed = 0
    area = (data.get('area') or '').strip()
    urgency = data.get('urgency') or 'urgent'
    needed_by_raw = data.get('neededBy')
    notes = data.get('notes') or ''

    field_errors = {}
    if not hospital_name:
        field_errors['hospitalName'] = 'Hospital name is required.'
    if not contact_name:
        field_errors['contactName'] = 'Contact name is required.'
    if not blood_group:
        field_errors['bloodGroup'] = 'Blood group is required.'
    if not area:
        field_errors['area'] = 'Area is required.'
    if units_needed < 1:
        field_errors['unitsNeeded'] = 'At least one unit is required.'
    if blood_group not in COMPATIBLE_DONORS_FOR_RECIPIENT:
        field_errors['bloodGroup'] = 'Select a valid blood group.'

    if field_errors:
        return Response(
            {"message": "Please correct the form errors.", "fieldErrors": field_errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    needed_by = timezone.now() + timezone.timedelta(hours=24)
    if needed_by_raw:
        try:
            needed_by = datetime.fromisoformat(needed_by_raw.replace('Z', '+00:00'))
        except Exception:
            pass

    # Reference generation e.g. REQ-2026-003
    count_today = BloodRequest.objects.count() + 1
    ref = f"REQ-2026-{count_today:03d}"

    blood_req = BloodRequest.objects.create(
        reference=ref,
        hospital_name=hospital_name,
        contact_name=contact_name,
        contact_phone=contact_phone,
        blood_group=blood_group,
        units_needed=units_needed,
        units_fulfilled=0,
        area=area,
        urgency=urgency,
        needed_by=needed_by,
        notes=notes,
        status='open'
    )

    # Match eligible compatible donors
    compatible_groups = COMPATIBLE_DONORS_FOR_RECIPIENT.get(blood_group, [blood_group])
    eligible_donors = list(
        Donor.objects.filter(
            blood_group__in=compatible_groups,
            eligible=True,
            consent_to_sms=True,
            opted_out=False,
            screening_status='clear'
        )
    )

    # Sort matching donors: same area first
    def sort_key(d):
        return (0 if area.lower() in d.location.lower() or d.location.lower() in area.lower() else 1, d.created_at)

    eligible_donors.sort(key=sort_key)

    # Create MatchedDonor links for up to 10 donors
    created_matches = []
    for donor in eligible_donors[:10]:
        match = MatchedDonor.objects.create(
            request=blood_req,
            donor=donor,
            response='pending',
            sms_status='not_sent'
        )
        created_matches.append(match)

    # Optional immediate dispatch on creation
    auto_dispatch = bool(data.get('autoDispatch', False))
    if auto_dispatch and created_matches:
        now = timezone.now()
        for m in created_matches:
            send_blood_alert_to_match(m)
        if any(m.sms_status in ('queued', 'sent', 'delivered') for m in created_matches):
            blood_req.sms_dispatched_at = now
            blood_req.status = 'notified'
        blood_req.save()

    return Response(serialize_blood_request(blood_req), status=status.HTTP_201_CREATED)

@api_view(['POST'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def request_dispatch_alerts(request, req_id):
    try:
        blood_req = BloodRequest.objects.get(id=req_id)
    except BloodRequest.DoesNotExist:
        return Response({"message": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

    # Queue/send real SMS alerts to all matched donors
    matches = list(blood_req.matched_donors.select_related('donor').all())
    now = timezone.now()
    for m in matches:
        send_blood_alert_to_match(m)

    sent_count = sum(1 for match in matches if match.sms_status in ('queued', 'sent', 'delivered'))
    if sent_count:
        blood_req.sms_dispatched_at = now
    if sent_count and blood_req.status == 'open':
        blood_req.status = 'notified'
    blood_req.save()

    if not sent_count:
        return Response({"message": "No SMS alerts were accepted by the provider. Check backend credentials and donor phone numbers.", "request": serialize_blood_request(blood_req)}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(serialize_blood_request(blood_req))

@api_view(['PATCH'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def request_update_status(request, req_id):
    try:
        blood_req = BloodRequest.objects.get(id=req_id)
    except BloodRequest.DoesNotExist:
        return Response({"message": "Blood request not found."}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get('status')
    if not new_status:
        return Response({"message": "Status is required."}, status=status.HTTP_400_BAD_REQUEST)

    # API rule: The frontend keeps a request from being marked fulfilled until its matched donors have been alerted.
    if new_status == 'fulfilled' and not blood_req.sms_dispatched_at:
        return Response(
            {"message": "Cannot mark request as fulfilled before SMS alerts have been dispatched."},
            status=status.HTTP_400_BAD_REQUEST
        )

    blood_req.status = new_status
    if new_status == 'fulfilled':
        blood_req.units_fulfilled = blood_req.units_needed
    blood_req.save()

    return Response(serialize_blood_request(blood_req))

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def drives_list(request):
    search = (request.query_params.get('search') or '').strip()
    status_filter = (request.query_params.get('status') or '').strip()

    qs = DonationDrive.objects.order_by('starts_at')
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(venue__icontains=search) |
            Q(area__icontains=search)
        )
    if status_filter:
        qs = qs.filter(status=status_filter)

    results = [serialize_donation_drive(d) for d in qs]
    return Response({
        "results": results,
        "count": len(results),
        "next": None,
        "previous": None
    })

@api_view(['GET'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def reports_summary(request):
    from_date = request.query_params.get('from')
    to_date = request.query_params.get('to')

    donor_qs = Donor.objects.all()
    req_qs = BloodRequest.objects.all()

    if from_date:
        try:
            dt = datetime.fromisoformat(from_date)
            donor_qs = donor_qs.filter(created_at__gte=dt)
            req_qs = req_qs.filter(created_at__gte=dt)
        except Exception:
            pass

    if to_date:
        try:
            dt = datetime.fromisoformat(to_date)
            donor_qs = donor_qs.filter(created_at__lte=dt)
            req_qs = req_qs.filter(created_at__lte=dt)
        except Exception:
            pass

    total_donors = donor_qs.count()
    eligible_donors = donor_qs.filter(eligible=True, opted_out=False).count()
    active_requests = req_qs.filter(status__in=['open', 'notified', 'partially_fulfilled']).count()
    fulfilled_sum = req_qs.aggregate(total=Sum('units_fulfilled'))['total'] or 0

    blood_groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    group_counts = {g: 0 for g in blood_groups}
    for item in donor_qs.values('blood_group').annotate(count=Count('blood_group')):
        bg = item['blood_group']
        if bg in group_counts:
            group_counts[bg] = item['count']

    recent_requests = [serialize_blood_request(req) for req in req_qs.order_by('-created_at')[:5]]

    return Response({
        "registeredDonors": total_donors,
        "eligibleDonors": eligible_donors,
        "activeRequests": active_requests,
        "livesSupported": fulfilled_sum,
        "donorsByBloodGroup": group_counts,
        "recentRequests": recent_requests
    })

@api_view(['POST'])
@authentication_classes([BearerAuthentication])
@permission_classes([AllowAny])
def sms_test_send(request):
    """
    Direct test SMS endpoint to verify phone number and Africa's Talking gateway connectivity.
    """
    phone = request.data.get('phoneNumber') or request.data.get('phone')
    if not phone:
        return Response({"message": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

    custom_msg = request.data.get('message')
    default_msg = (
        f"DamuLink Test Alert: SMS alerts are active and working! "
        f"Prepared for emergency blood matching notifications."
    )
    message = custom_msg if custom_msg else default_msg

    result = send_sms(phone, message)

    if result.get('success'):
        return Response({
            "message": f"Test SMS sent successfully to {phone}!",
            "status": result.get('status'),
            "details": result
        }, status=status.HTTP_200_OK)
    else:
        return Response({
            "message": result.get('error', 'Failed to send SMS'),
            "status": result.get('status', 'failed'),
            "details": result
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def sms_incoming_webhook(request):
    """
    Africa's Talking two-way SMS incoming webhook.
    Processes donor replies: YES, NO, or STOP.
    """
    data = request.data if request.data else request.POST or request.GET
    from_phone = data.get('from', '')
    text = data.get('text', '')

    if not from_phone or not text:
        return Response({"status": "error", "message": "Missing 'from' or 'text'"}, status=status.HTTP_400_BAD_REQUEST)

    result = handle_incoming_sms(from_phone, text)
    return Response(result, status=status.HTTP_200_OK)

