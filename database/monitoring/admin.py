from django.contrib import admin

from database.monitoring.models import PingHistory


@admin.register(PingHistory)
class PingHistoryAdmin(admin.ModelAdmin):
    list_display = ("ts", "total", "up", "avg_ms")
    date_hierarchy = "ts"
    show_full_result_count = False
    readonly_fields = ("ts", "total", "up", "avg_ms")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
