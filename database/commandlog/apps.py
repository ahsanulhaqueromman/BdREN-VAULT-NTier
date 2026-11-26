from django.apps import AppConfig


class CommandLogConfig(AppConfig):
    name = "database.commandlog"
    label = "commandlog"
    verbose_name = "Command History (device syslog)"
    default_auto_field = "django.db.models.BigAutoField"
