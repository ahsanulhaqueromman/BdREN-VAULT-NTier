from django.apps import AppConfig


class DevicesConfig(AppConfig):
    name = "persistence.devices"
    label = "devices"               # keeps the table names and migration history
    verbose_name = "Devices (switches, routers, OLTs)"
