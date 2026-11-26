from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared kernel: page registry, API helpers, background tasks and every manage.py command."""
    name = "core"
    label = "core"
    verbose_name = "Core (shared tools)"
