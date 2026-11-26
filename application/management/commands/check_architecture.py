"""python manage.py check_architecture  - verify the N-tier rules of application/core/architecture.py."""
from django.core.management.base import BaseCommand, CommandError

from application.core.architecture import check


class Command(BaseCommand):
    help = "Check the N-tier rules (presentation -> application -> persistence)."

    def handle(self, *args, **options):
        problems = check()
        if problems:
            for p in problems:
                self.stderr.write(str(p))
            raise CommandError(f"{len(problems)} architecture rule(s) broken. See application/core/architecture.py.")
        self.stdout.write(self.style.SUCCESS("Architecture OK: every app follows the N-tier rules."))
