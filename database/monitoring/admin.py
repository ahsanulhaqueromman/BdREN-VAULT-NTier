from django.contrib import admin

from database.monitoring.models import PingHistory

admin.site.register(PingHistory)
