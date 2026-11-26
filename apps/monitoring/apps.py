from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    name = "apps.monitoring"
    label = "monitoring"               # keeps the table names and migration history
    verbose_name = "Monitoring (ping, dashboard)"
