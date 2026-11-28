"""
Background threads: the backup scheduler and the ping monitor.

They run inside the process started by `python manage.py serve` (or alone with `manage.py run_background`
when the web server is gunicorn/uwsgi). Backup job progress lives in the database, so several
processes can safely share it.
"""
import logging
import sys
import threading
import time

from django.conf import settings
from django.db import connections

logger = logging.getLogger("dbms")
_START_LOCK = threading.Lock()
_STOP_EVENT = threading.Event()
_started = False


def stop_background():
    """Signal all background loops to exit cleanly."""
    _STOP_EVENT.set()


def _run_forever(name, func, interval, first_delay):
    def loop():
        if _STOP_EVENT.wait(first_delay):
            return
        while not _STOP_EVENT.is_set() and not sys.is_finalizing():
            try:
                func()
            except Exception:
                # Interpreter shutdown can begin while daemon background threads are alive.
                # Avoid noisy shutdown tracebacks; log normal runtime failures as before.
                if not sys.is_finalizing():
                    logger.exception("%s error", name)
            finally:
                try:
                    connections.close_all()          # each thread closes its own database connections
                except Exception:
                    pass
            if sys.is_finalizing():
                break
            _STOP_EVENT.wait(interval)
    threading.Thread(target=loop, name=name, daemon=True).start()


def _warm_backup_index():
    """Read every device's backup folder once, right after start, so the first visit to the Backups page
    does not wait for it (20,000 device folders take a while to list)."""
    from business.backups.services import warm_backup_index
    try:
        if _STOP_EVENT.wait(5):
            return
        warm_backup_index()
    except Exception:
        logger.warning("Could not pre-load the backup index", exc_info=True)
    finally:
        try:
            connections.close_all()
        except Exception:
            pass


def start_background():
    """Start the scheduler (checks every 30 s) and continuous full-inventory ping monitor. Safe twice."""
    global _started
    with _START_LOCK:
        if _started:
            return
        _started = True
    # background.py is the composition root of the periodic work: it only starts other apps' services.
    from business.backups.backup_jobs import close_stale_jobs
    from business.backups.services import run_retention
    from business.commandlog.services import prune_old_events
    from business.monitoring.services import ping_monitor_tick
    from business.radius.services import prune_old_logins
    from business.scheduling.services import scheduler_tick

    try:
        close_stale_jobs()
    except Exception:
        logger.warning("Could not close stale jobs on startup", exc_info=True)
    finally:
        try:
            connections.close_all()
        except Exception:
            pass
    threading.Thread(target=_warm_backup_index, name="backup-index", daemon=True).start()
    _run_forever("scheduler", scheduler_tick, 30, first_delay=30)
    _run_forever("retention", run_retention, 24 * 3600, first_delay=120)
    _run_forever("command-history-retention", prune_old_events, 24 * 3600, first_delay=180)
    _run_forever("radius-login-retention", prune_old_logins, 3600, first_delay=240)
    if settings.PING_SECONDS > 0:
        _run_forever("ping-monitor", ping_monitor_tick, max(15, settings.PING_SECONDS), first_delay=10)
