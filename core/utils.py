"""Small helpers shared by every app."""
import json

from django.utils import timezone

from core.exceptions import ApiError

DT_FORMAT = "%Y-%m-%d %H:%M:%S"


def _aware(value):
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_default_timezone())
    return value


def fmt_dt(value):
    """Datetime -> machine-readable Bangladesh-local 'YYYY-MM-DD HH:MM:SS'."""
    return timezone.localtime(_aware(value)).strftime(DT_FORMAT) if value else ""


def fmt_dt_ampm(value):
    """Datetime -> human-readable Bangladesh-local date/time with AM/PM."""
    return timezone.localtime(_aware(value)).strftime("%Y-%m-%d %I:%M:%S %p") if value else ""


def csv_safe(value):
    """A cell for a CSV file: text that a spreadsheet would run as a formula (=, +, -, @) is neutralised."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def parse_json(request):
    """JSON body of a request as a dict; raises ApiError(400) on invalid JSON or non-object payloads."""
    raw = request.body
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "Invalid JSON payload")
    if not isinstance(data, dict):
        raise ApiError(400, "JSON body must be an object")
    return data
