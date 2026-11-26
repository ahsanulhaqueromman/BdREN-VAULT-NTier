from django.conf import settings
from django.db import models
from django.utils import timezone

from core import crypto


class Device(models.Model):
    """A switch / router / OLT that is backed up over SSH. Passwords are stored encrypted."""
    name = models.CharField(max_length=100, blank=True)
    ip = models.CharField("IP or hostname", max_length=253, unique=True)
    device_type = models.CharField(max_length=40)
    port = models.PositiveIntegerField(default=22)
    username = models.CharField(max_length=150, blank=True)
    password = models.TextField(blank=True, help_text="Fernet-encrypted")
    secret = models.TextField("enable password", blank=True, help_text="Fernet-encrypted")
    command = models.CharField("custom command", max_length=500, blank=True)
    last_status = models.CharField(max_length=20, blank=True)
    last_run = models.DateTimeField(null=True, blank=True)
    schedule_override = models.BooleanField(default=False)
    schedule_days = models.CharField(max_length=100, default="1,15")
    schedule_time = models.CharField(max_length=5, default="02:00")
    schedule_last_date = models.CharField(max_length=10, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="created_devices")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name or self.ip

    # encrypted fields: use these instead of touching `password` / `secret` directly
    def set_password(self, raw):
        self.password = crypto.encrypt(raw)

    def get_password(self):
        return crypto.decrypt(self.password)

    def set_secret(self, raw):
        self.secret = crypto.encrypt(raw)

    def get_secret(self):
        return crypto.decrypt(self.secret)
