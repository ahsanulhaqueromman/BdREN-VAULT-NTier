"""Scheduling - read layer: stored settings, the retry queue and when the next automatic backup runs.

Selectors only read; every change is in services.py.
"""
import json
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from core.utils import DT_FORMAT

from database.scheduling.models import AppSetting

DEFAULTS = {"workers": None, "sched_on": "0", "sched_mode": "semimonthly", "sched_every": "60",
            "sched_at": "02:00", "sched_days": "1,15", "sched_catchup": "1", "sched_last": "0",
            "log_retention_months": "0"}
# Internal runtime keys must have defaults too. They are stored in AppSetting but are
# intentionally not exposed as editable form fields.
RUNTIME_DEFAULTS = {
    "pending_backup_device_ids": "[]",
    "pending_backup_ips": "[]",
    "pending_retry_after": "0",
    "queued_backup_device_ids": "[]",
    "initial_backup_pending": "0",
    "backup_job_heartbeat": "",
    "backup_job_cancel": "",
}
LOG_RETENTION_CHOICES = ("0", "12", "24", "48")   # months; "0" = keep logs forever
RETRY_INFO_KEY = "retry_info"


def retention_months():
    """Settings > "Keep logs and backup files for", in months; 0 = Forever (delete nothing)."""
    try:
        return max(int(get_setting("log_retention_months") or 0), 0)
    except ValueError:
        return 0


def retention_cutoff(now=None):
    """Everything older than this is deleted by the daily clean-up: Activity Logs, saved configuration files
    (the newest of each device stays), Session Log and accepted RADIUS logins. None = Forever.
    12 months = 365 days, 24 = 730, 48 = 1461."""
    months = retention_months()
    if not months:
        return None
    return (now or timezone.now()) - timedelta(days=round(months * 365.25 / 12))


def get_setting(key):
    """Value of one setting from the database, or its default."""
    row = AppSetting.objects.filter(key=key).first()
    if row:
        return row.value
    if key == "workers":
        return str(settings.WORKERS)
    if key in DEFAULTS:
        return str(DEFAULTS[key])
    # Unknown/missing internal settings should never crash the scheduler or import API.
    return RUNTIME_DEFAULTS.get(key, "")


def get_json_list(key):
    """A list kept as JSON in one setting; missing or damaged data gives []."""
    try:
        value = json.loads(get_setting(key) or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def get_id_list(key):
    """Device ids kept as a JSON list in one setting."""
    return [int(v) for v in get_json_list(key) if str(v).isdigit()]


def retry_info():
    try:
        value = json.loads(get_setting(RETRY_INFO_KEY) or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def all_settings():
    return {key: get_setting(key) for key in DEFAULTS}


def _schedule_days(values):
    """Return the configured days of month; invalid stored values safely fall back to 1 and 15."""
    try:
        days = sorted({int(x.strip()) for x in str(values.get("sched_days", "1,15")).split(",") if x.strip()})
        return days if days and all(1 <= day <= 31 for day in days) else [1, 15]
    except (TypeError, ValueError):
        return [1, 15]


def next_scheduled_run(values, now=None):
    """Next run as 'YYYY-MM-DD HH:MM' in the project time zone, or '' when the schedule is off."""
    if values["sched_on"] != "1":
        return ""
    now = now or datetime.now(timezone.get_current_timezone())
    last = float(values["sched_last"] or 0)
    if values["sched_mode"] == "semimonthly":
        at = datetime.strptime(values["sched_at"], "%H:%M").time()
        candidates = []
        days = _schedule_days(values)
        for offset in range(0, 14):
            month_index = now.month - 1 + offset
            year = now.year + month_index // 12
            month = month_index % 12 + 1
            import calendar
            for day in days:
                if day > calendar.monthrange(year, month)[1]:
                    continue
                candidate = datetime(year, month, day, at.hour, at.minute, tzinfo=now.tzinfo)
                last_day = datetime.fromtimestamp(last, now.tzinfo).date() if last > 0 else None
                if candidate >= now and not (candidate.date() == last_day):
                    candidates.append(candidate)
        if not candidates:
            month_index = now.month + 1
            year = now.year + (month_index - 1) // 12
            month = (month_index - 1) % 12 + 1
            import calendar
            candidates = [datetime(year, month, day, at.hour, at.minute, tzinfo=now.tzinfo)
                          for day in days if day <= calendar.monthrange(year, month)[1]]
        return min(candidates).strftime("%Y-%m-%d %H:%M")
    if values["sched_mode"] == "daily":
        at = datetime.strptime(values["sched_at"], "%H:%M").time()
        candidate = datetime.combine(now.date(), at, tzinfo=now.tzinfo)
        last_day = datetime.fromtimestamp(last, now.tzinfo).date() if last > 0 else None
        if candidate <= now:
            candidate = now if last_day != now.date() else candidate + timedelta(days=1)
        return candidate.strftime("%Y-%m-%d %H:%M")
    seconds = int(values["sched_every"]) * (86400 if values["sched_mode"] == "days" else 60)
    due = max(now.timestamp(), last + seconds)
    return datetime.fromtimestamp(due, now.tzinfo).strftime("%Y-%m-%d %H:%M")


def last_run_text(values):
    last = float(values["sched_last"] or 0)
    return datetime.fromtimestamp(last, timezone.get_current_timezone()).strftime(DT_FORMAT) if last > 0 else ""
