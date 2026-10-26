import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

def generate_uuid():
    return str(uuid.uuid4())

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('hospital_staff', 'Hospital Staff'),
        ('drive_staff', 'Drive Staff'),
    ]

    id = models.CharField(max_length=64, primary_key=True, default=generate_uuid)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default='hospital_staff')
    organization = models.CharField(max_length=255, default='DamuLink Health Network')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    objects = UserManager()

    def __str__(self):
        return f"{self.name} ({self.email})"

class AuthToken(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='auth_tokens')
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def generate_token(cls, user):
        token_key = uuid.uuid4().hex + uuid.uuid4().hex
        return cls.objects.create(key=token_key, user=user)

class Donor(models.Model):
    BLOOD_GROUPS = [
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    ]

    id = models.CharField(max_length=64, primary_key=True, default=generate_uuid)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=32)
    national_id = models.CharField(max_length=64)
    location = models.CharField(max_length=255)
    blood_group = models.CharField(max_length=8, choices=BLOOD_GROUPS)
    last_donation_date = models.DateTimeField(null=True, blank=True)
    eligible = models.BooleanField(default=True)
    consent_to_sms = models.BooleanField(default=True)
    opted_out = models.BooleanField(default=False)
    screening_status = models.CharField(max_length=32, default='clear')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.blood_group})"

class BloodRequest(models.Model):
    URGENCY_CHOICES = [
        ('routine', 'Routine'),
        ('urgent', 'Urgent'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('notified', 'Notified'),
        ('partially_fulfilled', 'Partially Fulfilled'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.CharField(max_length=64, primary_key=True, default=generate_uuid)
    reference = models.CharField(max_length=64, unique=True)
    hospital_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=32)
    blood_group = models.CharField(max_length=8)
    units_needed = models.IntegerField(default=1)
    units_fulfilled = models.IntegerField(default=0)
    area = models.CharField(max_length=255)
    urgency = models.CharField(max_length=16, choices=URGENCY_CHOICES, default='urgent')
    needed_by = models.DateTimeField()
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='open')
    sms_dispatched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.reference} - {self.hospital_name} ({self.blood_group})"

class MatchedDonor(models.Model):
    RESPONSE_CHOICES = [
        ('pending', 'Pending'),
        ('yes', 'Yes'),
        ('no', 'No'),
        ('opted_out', 'Opted Out'),
        ('failed', 'Failed'),
    ]
    SMS_STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('not_sent', 'Not Sent'),
    ]

    id = models.CharField(max_length=64, primary_key=True, default=generate_uuid)
    request = models.ForeignKey(BloodRequest, on_delete=models.CASCADE, related_name='matched_donors')
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='matches')
    response = models.CharField(max_length=16, choices=RESPONSE_CHOICES, default='pending')
    sms_status = models.CharField(max_length=16, choices=SMS_STATUS_CHOICES, default='not_sent')
    responded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Match {self.donor.full_name} -> {self.request.reference}"

class DonationDrive(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.CharField(max_length=64, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255)
    venue = models.CharField(max_length=255)
    area = models.CharField(max_length=255)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='scheduled')
    registered_donors = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.status})"
