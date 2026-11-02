from django.core.management.base import BaseCommand

from core.models import User


DEMO_USERS = [
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


class Command(BaseCommand):
    help = "Create or update the development demo accounts used by the frontend."

    def handle(self, *args, **options):
        for data in DEMO_USERS:
            user, _ = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "username": data["email"],
                    "name": data["name"],
                    "role": data["role"],
                    "organization": data["organization"],
                },
            )
            user.username = data["email"]
            user.name = data["name"]
            user.role = data["role"]
            user.organization = data["organization"]
            user.is_active = True
            user.set_password(data["password"])
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Provisioned {user.email} ({user.role})."))
