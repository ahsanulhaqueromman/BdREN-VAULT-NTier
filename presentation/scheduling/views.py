from django.http import JsonResponse

from application.backups.audit import record_audit
from presentation.core.api import api
from application.core.utils import parse_json

from application.scheduling import services


@api(GET="admin", PUT="admin")
def settings_view(request):
    """GET: settings + scheduler status for the Settings page. PUT: validate and save the form."""
    if request.method == "PUT":
        data = parse_json(request)
        services.save_settings(data)
        record_audit(request, "settings.update", "scheduler settings", ", ".join(sorted(str(k) for k in data)[:20]))
        return JsonResponse({"ok": True})
    from application.backups.jobs import job_running
    values = services.all_settings()
    values.update(sched_last_text=services.last_run_text(values),
                  next_run=services.next_scheduled_run(values), running=job_running())
    return JsonResponse(values)
