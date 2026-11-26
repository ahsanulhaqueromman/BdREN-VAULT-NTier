"""Command History API (administrators only). The page is templates/radius/commands.html.

    /api/radius/commands              GET  ?hours=24|168|720|2160|8760 or ?from=&to= (dates) &q= &kind=
                                           events + totals + receiver state (period: core/period.py)
    /api/radius/commands?format=csv   GET  the same filter as a CSV file (up to 50,000 rows)
    /api/radius/commands/sessions     GET  ?hours= &q= &user= &device=   sessions (login to logout); with user=
                                           or device=, or &export=1 (PDF export), each session also carries
                                           its commands
    /api/radius/commands/notes/<rejected|dropped>/dismiss  POST  clear that note (it comes back with the next one)
"""
import csv

from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone

from core import period as periods
from core.api import api
from core.utils import DT_FORMAT

from apps.commandlog.selectors import command_log_selectors as q
from apps.commandlog.services import command_log_service as services

CSV_LIMIT = 50000


def _when(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime(DT_FORMAT)


def _period(request):
    """(keyword arguments for the selectors, the period as the browser gets it back)"""
    p = periods.from_request(request)
    return {"hours": p["hours"] or 24, "since": p["since"], "until": p["until"]}, periods.public(p)


@api(GET="admin")
def commands(request):
    search, kind = request.GET.get("q", ""), request.GET.get("kind", "")
    when, shown = _period(request)
    if request.GET.get("format") == "csv":
        return _csv(q.history(q=search, kind=kind, limit=CSV_LIMIT, **when))
    data = q.history(q=search, kind=kind, **when)
    for e in data["events"]:
        e["ts"] = _when(e["ts"])
    status = q.receiver_status()
    status["heartbeat"], status["rejected_at"] = _when(status.get("heartbeat")), _when(status.get("rejected_at"))
    sources = q.sources()
    for s in sources:
        s["first_seen"], s["last_seen"] = _when(s["first_seen"]), _when(s["last_seen"])
    return JsonResponse({**data, "receiver": status, "sources": sources, "period": shown})


@api(POST="admin")
def dismiss_note(request, note):
    if not services.dismiss_note(note):
        raise Http404
    return JsonResponse({"ok": True})


@api(GET="admin")
def sessions(request):
    user = request.GET.get("user", "").strip()[:64]
    device = request.GET.get("device", "").strip()[:45]
    when, shown = _period(request)
    # ?export=1 (the Session Log "Export PDF" button): every matching session's commands, not just one
    # user's or one device's - the same cost as the normal list (events are already built), just not stripped.
    with_events = bool(user or device or request.GET.get("export"))
    data = q.sessions(q=request.GET.get("q", ""), user=user, device=device, with_events=with_events, **when)
    for s in data["sessions"]:
        for key in ("start", "end", "last"):
            s[key] = _when(s[key])
        for e in s["events"]:
            e["ts"] = _when(e["ts"])
    return JsonResponse({**data, "user": user, "device": device, "period": shown})


def _csv(data):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="command-history-{stamp}.csv"'
    response["Cache-Control"] = "no-store, private"
    response.write("﻿")                       # so Excel reads the file as UTF-8
    out = csv.writer(response)
    out.writerow(["Time", "User", "Device", "Device IP", "From", "Type", "Command", "Result"])
    for e in data["events"]:
        out.writerow([_when(e["ts"]), _safe(e["username"]), _safe(e["device"]), e["device_ip"], e["source_ip"],
                      e["kind"], _safe(e["command"]), _safe(e["result"])])
    return response


def _safe(value):
    """A cell that starts with = + - @ is run as a formula by spreadsheet programs: keep it text."""
    value = value or ""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value
