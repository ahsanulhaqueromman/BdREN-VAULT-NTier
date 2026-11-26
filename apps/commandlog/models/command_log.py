from django.db import models
from django.utils import timezone


class CommandEvent(models.Model):
    """One thing a user did on a network device, read from the device's syslog: a command, a configuration
    change, a login or a logout. Written only by the syslog receiver (manage.py syslog_receive)."""
    KIND_CHOICES = [("command", "Command"), ("change", "Change"), ("login", "Login"), ("logout", "Logout"),
                    ("login-failed", "Failed login")]
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    device_ip = models.CharField(max_length=45)          # the device that sent the message
    username = models.CharField(max_length=64)
    source_ip = models.CharField(max_length=64, blank=True, default="")   # where the user connected from
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    command = models.CharField(max_length=1000, blank=True, default="")
    result = models.CharField(max_length=32, blank=True, default="")
    vendor = models.CharField(max_length=16, blank=True, default="")

    class Meta:
        ordering = ["-received_at", "-id"]
        indexes = [models.Index(fields=["device_ip", "received_at"], name="cmdlog_device_time"),
                   models.Index(fields=["username", "received_at"], name="cmdlog_user_time")]


class SyslogSource(models.Model):
    """Every device that sends syslog to VAULT: how many messages arrived and how many were user actions.
    The last message that was not recognised is kept so a new device type can be checked."""
    ip = models.CharField(max_length=45, unique=True)
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    received = models.PositiveBigIntegerField(default=0)
    recognized = models.PositiveBigIntegerField(default=0)
    last_unrecognized = models.CharField(max_length=500, blank=True, default="")
    hostname = models.CharField(max_length=64, blank=True, default="")   # as the device writes it in its messages


class ReceiverState(models.Model):
    """One row (id=1): the syslog receiver's heartbeat, so the page can say whether it is running."""
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    port = models.PositiveIntegerField(default=514)
    rejected = models.PositiveBigIntegerField(default=0)     # messages from addresses that are not devices
    rejected_last_ip = models.CharField(max_length=45, blank=True, default="")
    rejected_at = models.DateTimeField(null=True, blank=True)   # when the newest refused message came
    dropped = models.PositiveBigIntegerField(default=0)      # over the per-device rate limit
