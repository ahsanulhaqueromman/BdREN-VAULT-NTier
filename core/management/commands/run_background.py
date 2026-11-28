"""Only the background jobs (for setups where gunicorn/uwsgi serves the web pages)."""
import signal
import threading

from django.core.management.base import BaseCommand

from core.background import start_background, stop_background


class Command(BaseCommand):
    help = "Run the backup scheduler and ping monitor without a web server."

    def handle(self, *args, **opts):
        stop = threading.Event()

        def _handle_signal(_signum, _frame):
            stop.set()
            stop_background()

        signal.signal(signal.SIGINT, _handle_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handle_signal)

        start_background()
        self.stdout.write("Background scheduler running. Press Ctrl+C to stop.")
        stop.wait()
