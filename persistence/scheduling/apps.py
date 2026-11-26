from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "persistence.scheduling"
    label = "scheduling"               # keeps the table names and migration history
    verbose_name = "Scheduling (automatic backups, settings)"
