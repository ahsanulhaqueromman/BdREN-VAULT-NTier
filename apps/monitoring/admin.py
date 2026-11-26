from django.contrib import admin

from apps.monitoring.models import PingHistory

admin.site.register(PingHistory)
