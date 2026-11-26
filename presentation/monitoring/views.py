"""Monitoring - HTTP layer: /api/ping (ping column), /api/dashboard (Dashboard numbers) and
/api/dashboard/ssh (the Active Sessions card, refreshed on its own every 10 s)."""
from django.http import JsonResponse

from core.api import api

from business.backups import backup_jobs
from data_access.monitoring import selectors
from business.monitoring import services


@api(GET="viewer")
def ping_all(request):
    """Ping devices in parallel -> {device id: {up, ms}}. ?ids=1,2,3 pings only those (rows on screen)."""
    wanted = {int(x) for x in (request.GET.get("ids") or "").split(",") if x.strip().isdigit()}
    return JsonResponse(services.ping_devices(wanted))


@api(GET="viewer")
def dashboard(request):
    """Numbers for the Dashboard graphs: backups per day, uptime history, vendors, next scheduled run."""
    backup_jobs.close_stale_jobs()          # a job whose process died is not shown as running
    return JsonResponse(selectors.dashboard(show_internals=request.user.has_role("admin")))


@api(GET="admin")
def dashboard_ssh(request):
    """Administrators: who is signed in to a device right now (the Dashboard's Active Sessions card)."""
    return JsonResponse({"ssh": selectors.active_sessions()})
