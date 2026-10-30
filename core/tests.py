from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from .models import BloodRequest, Donor, MatchedDonor
from .views import requests_list_or_create, request_dispatch_alerts


class BloodRequestMatchingTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.donor = Donor.objects.create(
            full_name='Eligible Donor', phone_number='+254712345678', national_id='ID-1',
            location='Nairobi', blood_group='B+', eligible=True, consent_to_sms=True,
            opted_out=False, screening_status='clear',
        )

    def test_candidate_lookup_returns_compatible_donors_only(self):
        request = self.factory.get('/api/requests', {'bloodGroup': 'B+', 'area': 'Nairobi'})
        response = requests_list_or_create(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['phoneNumber'], self.donor.phone_number)

    def test_failed_sms_does_not_mark_request_notified(self):
        blood_request = BloodRequest.objects.create(
            reference='REQ-TEST-001', hospital_name='Test Hospital', contact_name='Staff',
            contact_phone='+254700000000', blood_group='B+', units_needed=1, area='Nairobi',
            needed_by=timezone.now() + timedelta(hours=1),
        )
        match = MatchedDonor.objects.create(request=blood_request, donor=self.donor)
        request = self.factory.post(f'/api/requests/{blood_request.id}/alerts', {}, format='json')
        response = request_dispatch_alerts(request, blood_request.id)
        blood_request.refresh_from_db()
        match.refresh_from_db()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(match.sms_status, 'failed')
        self.assertIsNone(blood_request.sms_dispatched_at)
