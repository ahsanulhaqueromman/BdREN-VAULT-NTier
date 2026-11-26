"""The period a log page shows: a recent window ("last 7 days") or any range of calendar dates.

Authentication Audit and Session Log read the same query string:

    ?hours=24 | 168 | 720 | 2160 | 8760     the last 24 hours, 7 days, 30 days, 90 days or year
    ?from=2026-01-01&to=2026-01-31          whole local days, both ends included (Asia/Dhaka)

How far back data exists is set by System Settings > Keep logs and backup files for.
"""
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from application.core.errors import ApiError

PRESETS = {24: "in the last 24 hours", 168: "in the last 7 days", 720: "in the last 30 days",
           2160: "in the last 90 days", 8760: "in the last year"}
MAX_DAYS = 3 * 366          # one request covers at most about three years


def _day(value):
    return f"{value.day} {value:%b %Y}"


def from_request(request, default=24):
    """{"since", "until" (aware datetimes; until None = up to now), "hours", "from", "to", "label"}."""
    start, end = request.GET.get("from", "").strip(), request.GET.get("to", "").strip()
    if start or end:
        try:
            first = date.fromisoformat(start or end)
            last = date.fromisoformat(end or start)
        except ValueError:
            raise ApiError(400, "Choose a valid start and end date.")
        if last < first:
            first, last = last, first
        if (last - first).days >= MAX_DAYS:
            raise ApiError(400, "Choose a period of at most three years.")
        tz = timezone.get_current_timezone()
        since = timezone.make_aware(datetime.combine(first, time.min), tz)
        until = timezone.make_aware(datetime.combine(last + timedelta(days=1), time.min), tz)
        label = f"on {_day(first)}" if first == last else f"from {_day(first)} to {_day(last)}"
        return {"since": since, "until": until, "hours": None, "from": first.isoformat(), "to": last.isoformat(),
                "label": label}
    try:
        hours = int(request.GET.get("hours", default))
    except ValueError:
        hours = default
    if hours not in PRESETS:
        hours = default
    return {"since": timezone.now() - timedelta(hours=hours), "until": None, "hours": hours, "from": "", "to": "",
            "label": PRESETS[hours]}


def public(period):
    """The part the browser gets back (no datetimes)."""
    return {k: period[k] for k in ("hours", "from", "to", "label")}
