from django.apps import AppConfig


class ApplicationConfig(AppConfig):
    """Tier 2. Registered only so Django finds the management commands in application/management/commands/."""
    name = "application"
    label = "vault_application"
    verbose_name = "Application tier (services, selectors, commands)"
