from django.apps import AppConfig


class BackupsConfig(AppConfig):
    name = "persistence.backups"
    label = "backups"               # keeps the table names and migration history
    verbose_name = "Backups (SSH engine, files, jobs, logs)"
