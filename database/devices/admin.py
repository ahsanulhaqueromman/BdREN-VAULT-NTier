from django.contrib import admin

from database.devices.models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("ip", "name", "device_type", "last_status", "last_run")
    list_filter = ("device_type", "last_status", "schedule_override")
    search_fields = ("ip", "name")
    exclude = ("password", "secret")          # encrypted values are never shown in the admin
    readonly_fields = ("last_status", "last_run", "schedule_last_date", "created_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
