import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import User, Donor, BloodRequest, MatchedDonor, DonationDrive
from core.serializers import COMPATIBLE_DONORS_FOR_RECIPIENT

class Command(BaseCommand):
    help = 'Seeds initial users, screened donors, sample blood requests and donation drives'

    def handle(self, *args, **options):
        self.stdout.write("Seeding DamuLink data...")

        # 1. Seed Users
        users_data = [
            {
                "email": "admin@damulink.local",
                "password": "DamuLinkAdmin!2026",
                "name": "DamuLink Admin",
                "role": "admin",
                "organization": "Demo workspace",
            },
            {
                "email": "hospital@damulink.local",
                "password": "DamuLinkHospital!2026",
                "name": "Hospital Staff",
                "role": "hospital_staff",
                "organization": "Demo hospital",
            },
            {
                "email": "drive@damulink.local",
                "password": "DamuLinkDrive!2026",
                "name": "Drive Staff",
                "role": "drive_staff",
                "organization": "Demo donation drive",
            },
        ]

        for u_info in users_data:
            user, created = User.objects.get_or_create(
                email=u_info['email'],
                defaults={
                    'username': u_info['email'],
                    'name': u_info['name'],
                    'role': u_info['role'],
                    'organization': u_info['organization']
                }
            )
            user.set_password(u_info['password'])
            user.name = u_info['name']
            user.role = u_info['role']
            user.organization = u_info['organization']
            user.save()
            self.stdout.write(f"User {user.email} prepared.")

        # 2. Seed Donors
        sample_donors = [
            ("Amina Wanjiku", "+254 712 345 678", "28374819", "Nairobi CBD", "O-", 120),
            ("Brian Ochieng", "+254 723 456 789", "30928172", "Westlands", "O+", 60),
            ("Catherine Nduta", "+254 734 567 890", "31829304", "Upper Hill", "A+", 90),
            ("David Kiprono", "+254 745 678 901", "29482910", "Parklands", "A-", 150),
            ("Esther Muthoni", "+254 756 789 012", "33910293", "Kilimani", "B+", 45),
            ("Felix Mutua", "+254 767 890 123", "27481920", "Karen", "B-", 180),
            ("Grace Akinyi", "+254 778 901 234", "32948102", "Kasarani", "AB+", 75),
            ("Hassan Omar", "+254 789 012 345", "34910283", "South C", "AB-", 110),
            ("Ivy Chebet", "+254 790 123 456", "29102938", "Nairobi West", "O+", 30),
            ("Joseph Karanja", "+254 701 234 567", "35829102", "Upper Hill", "O-", 200),
            ("Kennedy Otieno", "+254 711 223 344", "26481920", "Westlands", "A+", 40),
            ("Lilian Wambui", "+254 722 334 455", "31029384", "Kilimani", "B+", 85),
        ]

        now = timezone.now()
        for name, phone, nat_id, loc, bg, days_ago in sample_donors:
            last_date = now - timedelta(days=days_ago)
            donor, _ = Donor.objects.get_or_create(
                national_id=nat_id,
                defaults={
                    'full_name': name,
                    'phone_number': phone,
                    'location': loc,
                    'blood_group': bg,
                    'last_donation_date': last_date,
                    'eligible': True,
                    'consent_to_sms': True,
                    'opted_out': False,
                    'screening_status': 'clear',
                }
            )

        self.stdout.write(f"Screened donors prepared: {Donor.objects.count()}.")

        # 3. Seed Blood Requests
        if BloodRequest.objects.count() == 0:
            # Request 1: Critical O- at Kenyatta National Hospital
            req1 = BloodRequest.objects.create(
                reference="REQ-2026-001",
                hospital_name="Kenyatta National Hospital",
                contact_name="Dr. Sarah Kamau",
                contact_phone="+254 722 000 111",
                blood_group="O-",
                units_needed=2,
                units_fulfilled=0,
                area="Upper Hill",
                urgency="critical",
                needed_by=now + timedelta(hours=12),
                notes="Immediate trauma surgery unit requirement.",
                status="open",
            )
            # Find matching donors (O-)
            compatible1 = COMPATIBLE_DONORS_FOR_RECIPIENT.get("O-", ["O-"])
            donors1 = Donor.objects.filter(blood_group__in=compatible1, eligible=True)
            for d in donors1:
                MatchedDonor.objects.create(
                    request=req1,
                    donor=d,
                    response='pending',
                    sms_status='not_sent'
                )

            # Request 2: Fulfilled A+ at Aga Khan Hospital
            req2 = BloodRequest.objects.create(
                reference="REQ-2026-002",
                hospital_name="Aga Khan University Hospital",
                contact_name="Dr. Dennis Mwangi",
                contact_phone="+254 733 111 222",
                blood_group="A+",
                units_needed=3,
                units_fulfilled=3,
                area="Parklands",
                urgency="urgent",
                needed_by=now - timedelta(days=1),
                notes="Oncology ward transfusions completed.",
                status="fulfilled",
                sms_dispatched_at=now - timedelta(days=2),
            )
            compatible2 = COMPATIBLE_DONORS_FOR_RECIPIENT.get("A+", ["A+"])
            donors2 = Donor.objects.filter(blood_group__in=compatible2, eligible=True)[:4]
            for i, d in enumerate(donors2):
                MatchedDonor.objects.create(
                    request=req2,
                    donor=d,
                    response='yes' if i < 3 else 'no',
                    sms_status='delivered',
                    responded_at=now - timedelta(days=1, hours=20 - i)
                )

            # Request 3: Notified B+ at MP Shah Hospital
            req3 = BloodRequest.objects.create(
                reference="REQ-2026-003",
                hospital_name="MP Shah Hospital",
                contact_name="Sister Rose Anyango",
                contact_phone="+254 711 999 888",
                blood_group="B+",
                units_needed=2,
                units_fulfilled=1,
                area="Westlands",
                urgency="urgent",
                needed_by=now + timedelta(days=1),
                notes="Maternity department blood reserve.",
                status="notified",
                sms_dispatched_at=now - timedelta(hours=3),
            )
            compatible3 = COMPATIBLE_DONORS_FOR_RECIPIENT.get("B+", ["B+"])
            donors3 = Donor.objects.filter(blood_group__in=compatible3, eligible=True)[:3]
            for i, d in enumerate(donors3):
                MatchedDonor.objects.create(
                    request=req3,
                    donor=d,
                    response='yes' if i == 0 else 'pending',
                    sms_status='sent',
                    responded_at=now - timedelta(hours=1) if i == 0 else None
                )

        self.stdout.write(f"Blood requests prepared: {BloodRequest.objects.count()}.")

        # 4. Seed Donation Drives
        sample_drives = [
            ("Nairobi CBD Blood Drive", "Kencom Bus Stage Plaza", "Nairobi CBD", now + timedelta(days=3), now + timedelta(days=3, hours=8), "scheduled", 48),
            ("Westlands Community Blood Camp", "Sarit Centre Expo", "Westlands", now - timedelta(hours=4), now + timedelta(hours=4), "active", 65),
            ("Upper Hill Health & Blood Drive", "Nairobi Hospital Grounds", "Upper Hill", now - timedelta(days=7), now - timedelta(days=7, hours=-8), "completed", 124),
        ]

        for name, venue, area, starts, ends, status_val, reg_donors in sample_drives:
            DonationDrive.objects.get_or_create(
                name=name,
                defaults={
                    'venue': venue,
                    'area': area,
                    'starts_at': starts,
                    'ends_at': ends,
                    'status': status_val,
                    'registered_donors': reg_donors
                }
            )

        self.stdout.write(f"Donation drives prepared: {DonationDrive.objects.count()}.")
        self.stdout.write(self.style.SUCCESS("DamuLink database seeded successfully!"))
