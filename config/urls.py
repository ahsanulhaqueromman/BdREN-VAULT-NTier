"""Root URL table.

Pages (HTML) come from the page registry in core/pages.py; every app owns the JSON API under /api/
in its own urls.py, plugged in below.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from core import views as core_views
from core.pages import PAGES

urlpatterns = [
    path("", core_views.index, name="index"),
    path("healthz", core_views.healthz, name="healthz"),
    path("robots.txt", core_views.robots_txt, name="robots-txt"),
    # ---- pages: one URL per screen (/dashboard, /devices, /radius/users, ...) ----
    *[path(p.path, core_views.page_view, {"key": p.key}, name=f"page-{p.key}") for p in PAGES],
    path("devices/<int:pk>", core_views.device_page, name="page-device"),
    # ---- sign-in and JSON API ----
    path("", include("presentation.accounts.urls")),        # /setup /login /logout /api/me /api/users
    path("", include("presentation.devices.urls")),         # /api/devices /api/credentials
    path("", include("presentation.backups.urls")),         # /api/backup /api/backups /api/logs /api/diff
    path("", include("presentation.scheduling.urls")),      # /api/settings
    path("", include("presentation.monitoring.urls")),      # /api/ping /api/dashboard
    path("", include("presentation.radius.urls")),          # /api/radius/users /api/radius/nas /api/radius/audit
    path("", include("presentation.commandlog.urls")),      # /api/radius/commands
]

if settings.ENABLE_ADMIN_SITE:        # off by default: every login page on the internet gets attacked
    urlpatterns.insert(2, path("admin/", admin.site.urls))
