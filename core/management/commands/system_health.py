"""Read-only operational checks for the VAULT host."""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = "Run read-only database, key, backup-folder, and disk-space health checks."

    def handle(self, *args, **opts):
        issues = 0

        def report(label, ok, detail):
            nonlocal issues
            if not ok:
                issues += 1
            style = self.style.SUCCESS if ok else self.style.WARNING
            self.stdout.write(style(f"{'OK' if ok else 'CHECK'} | {label} | {detail}"))

        try:
            connections['default'].ensure_connection()
            with connections['default'].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            report("database", True, "connection and simple query succeeded")
        except Exception as exc:
            report("database", False, f"database connection failed ({type(exc).__name__})")

        data_dir = Path(settings.DATA_DIR)
        backup_dir = Path(settings.BACKUP_DIR)
        key = Path(settings.FERNET_KEY_FILE)
        report("data directory", data_dir.is_dir(), str(data_dir))
        report("backup directory", backup_dir.is_dir() and backup_dir.exists(), str(backup_dir))
        import os
        import stat
        key_ok = key.is_file() and not key.is_symlink() and key.stat().st_size > 0
        key_perm_ok = key_ok and (os.name != "posix" or (stat.S_IMODE(key.stat().st_mode) & 0o077) == 0)
        report("encryption key", key_perm_ok,
               "key file exists with owner-only permissions" if key_perm_ok else "key file missing or overly permissive")
        try:
            usage = shutil.disk_usage(backup_dir if backup_dir.exists() else data_dir)
            free_pct = (usage.free / usage.total * 100) if usage.total else 0
            report("disk free space", free_pct >= 15,
                   f"{usage.free / (1024**3):.1f} GiB free ({free_pct:.1f}%); warning threshold 15%")
        except OSError as exc:
            report("disk free space", False, str(exc))
        report("debug mode", not settings.DEBUG, "DEBUG is off" if not settings.DEBUG else "DEBUG is on; turn it off for production")
        hosts_ok = "*" not in settings.ALLOWED_HOSTS
        report("allowed hosts", hosts_ok,
               "explicit host list configured" if hosts_ok else "DJANGO_ALLOWED_HOSTS contains wildcard '*'; restrict it before production")
        report("worker limit", 1 <= settings.WORKERS <= settings.MAX_WORKERS, f"WORKERS={settings.WORKERS}; recommended starting value 10; hard cap 20")
        self.stdout.write(f"Health check completed at {timezone.localtime():%Y-%m-%d %H:%M:%S}; checks needing attention: {issues}")
