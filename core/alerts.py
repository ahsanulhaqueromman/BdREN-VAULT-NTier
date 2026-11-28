"""Optional failure notifications. Disabled unless explicitly configured in environment."""
import logging
import os
import threading
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

log = logging.getLogger(__name__)


def _send_alerts(title, body, token, chat_id, recipients):
    if token and chat_id:
        try:
            data = urllib.parse.urlencode({"chat_id": chat_id, "text": body}).encode()
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
            with urllib.request.urlopen(req, timeout=3) as response:
                response.read(256)
        except Exception as exc:
            log.warning("Telegram failure alert could not be delivered (%s)", type(exc).__name__)
    if recipients:
        try:
            send_mail(title, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), recipients,
                      fail_silently=False)
        except Exception as exc:
            log.warning("Email failure alert could not be delivered (%s)", type(exc).__name__)


def notify_backup_failure(device, message):
    """Dispatch configured alerts asynchronously with short timeouts; never block or fail a backup."""
    token = os.environ.get("DBMS_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("DBMS_TELEGRAM_CHAT_ID", "").strip()
    recipients = [x.strip() for x in os.environ.get("DBMS_ALERT_EMAILS", "").split(",") if x.strip()]
    if not (token and chat_id) and not recipients:
        return
    title = f"VAULT FAILED: {getattr(device, 'name', '') or device.ip} ({device.ip})"
    body = f"{title}\nTime: {timezone.now()}\nDetails: {str(message)[:1500]}"
    threading.Thread(
        target=_send_alerts,
        args=(title, body, token, chat_id, recipients),
        daemon=True,
        name="vault-alert",
    ).start()
