from django.contrib import admin

from database.backups.models import BackupLog


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ("ts", "ip", "name", "status", "message")
    list_filter = ("status",)
    search_fields = ("ip", "name")
    date_hierarchy = "ts"
    show_full_result_count = False
    readonly_fields = ("ts", "ip", "name", "status", "message")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
