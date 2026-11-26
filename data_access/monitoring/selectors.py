"""Monitoring - read layer: the Dashboard numbers and server health.

Backup and device numbers come from those apps' selectors; this module only combines them.
"""
import logging
import shutil
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from data_access.backups import selectors as backups
from core.utils import fmt_dt
from data_access.devices import selectors as devices
from data_access.devices.vendor_registry import VENDORS
from data_access.scheduling import selectors as scheduling

from data_access.monitoring.cache_keys import LATEST_KEY
from database.monitoring.models import PingHistory

SHOW = 6    # rows per Dashboard list; the card says how many more there are
CHART_POINTS = 288      # uptime chart: a 640-pixel line needs no more; a 60 s sweep writes 1,440 a day


def database_info():
    """Size of the application database (MySQL / MariaDB) for the Dashboard card."""
    name = str(settings.DATABASES["default"].get("NAME", ""))
    try:
        if connection.vendor == "mysql":
            with connection.cursor() as cur:
                cur.execute("SELECT COALESCE(SUM(data_length + index_length), 0) "
                            "FROM information_schema.tables WHERE table_schema = DATABASE()")
                return {"engine": "MySQL / MariaDB", "name": name, "bytes": int(cur.fetchone()[0] or 0)}
    except Exception:
        logging.getLogger("dbms").warning("Could not read the database size", exc_info=True)
    return {"engine": connection.vendor, "name": name, "bytes": None}


def disk_health():
    """Free space where the backups are stored (no recursive scan: cheap on every refresh)."""
    disk_path = settings.BACKUP_DIR if settings.BACKUP_DIR.exists() else settings.DATA_DIR
    try:
        disk = shutil.disk_usage(str(disk_path))
        return {"total_bytes": disk.total, "free_bytes": disk.free,
                "used_percent": round((disk.used / disk.total) * 100, 1) if disk.total else 0,
                "status": "critical" if disk.free < 2 * 1024**3 or (disk.total and disk.free / disk.total < .05)
                          else "warning" if disk.total and disk.free / disk.total < .15 else "ok"}
    except OSError:
        return {"total_bytes": 0, "free_bytes": 0, "used_percent": None, "status": "unknown"}


def ping_history(hours=24, points=CHART_POINTS):
    """Reachability over the last `hours`, oldest first. Sweeps are averaged in equal groups so the
    Dashboard (refreshed every 30 s) sends at most `points` rows; the newest sweep is always kept as it is,
    because the "Online (last check)" tile reads it."""
    rows = list(PingHistory.objects.filter(ts__gte=timezone.now() - timedelta(hours=hours))
                .order_by("ts").values_list("ts", "total", "up", "avg_ms"))
    if not rows:
        return []
    last, rest = rows[-1], rows[:-1]
    size = -(-len(rest) // max(1, points - 1)) if rest else 1
    out = []
    for i in range(0, len(rest), size):
        group = rest[i:i + size]
        ms = [r[3] for r in group if r[3] is not None]
        out.append((group[-1][0], round(sum(r[1] for r in group) / len(group)),
                    round(sum(r[2] for r in group) / len(group)), round(sum(ms) / len(ms), 1) if ms else None))
    out.append(last)
    return [{"ts": fmt_dt(ts), "total": total, "up": up, "avg_ms": avg} for ts, total, up, avg in out]


def attention():
    """Devices that need a look now: offline in the monitor's latest sweep, and devices whose last backup failed
    (with the error), plus how many wait for an automatic retry. offline_count is None while the background
    ping monitor has no sweep yet (or is off)."""
    from django.core.cache import cache
    latest = cache.get(LATEST_KEY)
    offline, offline_count = [], None
    if latest:
        down = sorted(int(k) for k, r in latest.items() if not (r or {}).get("up"))
        offline_count = len(down)
        offline = [{"id": d.id, "name": d.name, "ip": d.ip} for d in devices.devices_with_pks(down[:SHOW])]
    failing = devices.failing_devices()
    shown = failing[:SHOW]
    why = backups.last_failure_messages([d["ip"] for d in shown])
    failed = [{"id": d["id"], "name": d["name"], "ip": d["ip"], "ts": fmt_dt(d["last_run"]) if d["last_run"] else "",
               "message": (why.get(d["ip"]) or "")[:160]} for d in shown]
    return {"offline": offline, "offline_count": offline_count, "failed": failed, "failed_count": len(failing),
            "retry_count": len(backups.retry_queue())}


def recent_changes():
    """The newest saved configuration changes, linked to their device when it still exists."""
    rows = backups.recent_changes(SHOW)
    ids = {d.ip: d.id for d in devices.devices_with_ips({r["ip"] for r in rows})}
    return [{**r, "id": ids.get(r["ip"])} for r in rows]


def device_access():
    """Administrators: device logins through RADIUS in the last 24 hours, and accepted logins outside a
    user's allowed devices. None when the RADIUS database is not reachable (the card is then hidden)."""
    from django.core.cache import cache

    from data_access.radius import selectors as radius
    cached = cache.get("dash-access")      # the Dashboard refreshes every 30 s; RADIUS is read once a minute
    if cached is not None:
        return cached or None
    try:
        summary = {**radius.login_summary(24), "violations": len(radius.limit_violations(24))}
    except Exception:
        logging.getLogger("dbms").info("Dashboard: RADIUS login summary unavailable", exc_info=True)
        summary = {}
    cache.set("dash-access", summary, 60)
    return summary or None


def active_sessions():
    """Administrators: who is signed in to a device over SSH right now, from the Session Log (a session with no
    logout and activity in the last 5 minutes). Read at most every 5 s (the card asks every 10 s).
    None when it cannot be read."""
    from django.core.cache import cache

    from data_access.commandlog import selectors as commandlog
    cached = cache.get("dash-ssh")
    if cached is not None:
        return cached or None
    try:
        now = timezone.now()
        live = [s for s in commandlog.sessions(hours=24)["sessions"] if s["status"] == "active"]
        ids = {d.ip: d.id for d in devices.devices_with_ips({s["device_ip"] for s in live})}
        rows = [{"key": s["key"], "user": s["username"], "device": s["device"], "ip": s["device_ip"],
                 "id": ids.get(s["device_ip"]),
                 "from": s["source_ip"], "since": fmt_dt(s["start"] or s["last"]),
                 "for_s": int((now - (s["start"] or s["last"])).total_seconds()),
                 "last": fmt_dt(s["last"]), "commands": s["commands"], "changes": s["changes"]} for s in live]
        out = {"count": len(rows), "users": len({r["user"] for r in rows}), "devices": len({r["ip"] for r in rows}),
               "rows": rows[:SHOW]}
    except Exception:
        logging.getLogger("dbms").info("Dashboard: active sessions unavailable", exc_info=True)
        out = {}
    cache.set("dash-ssh", out, 5)
    return out or None


def last_job():
    """The newest backup run: when, why, how long and its result counts (None before the first run)."""
    jobs = backups.job_history(1)["jobs"]
    if not jobs:
        return None
    j = jobs[0]
    return {k: j[k] for k in ("started", "finished", "finished_at", "duration_s", "total", "done", "counts",
                              "reason_label")}


def syslog_receiver():
    """Administrators: is the Session Log's syslog receiver running, and when did it last report."""
    from data_access.commandlog import selectors as commandlog
    st = commandlog.receiver_status()
    return {"running": st["running"], "seen": st.get("seen", False),
            "heartbeat": fmt_dt(st["heartbeat"]) if st.get("heartbeat") else ""}


def dashboard(show_internals):
    """Numbers for the Dashboard: backups per day, uptime history, vendors, results, schedule and health.
    show_internals=False (non-administrators) hides the database engine and name."""
    today = timezone.localdate()
    per_day = backups.results_per_day([today - timedelta(days=i) for i in range(13, -1, -1)])
    vendors, status, total = {}, {"SUCCESS": 0, "UNCHANGED": 0, "FAILED": 0, "NONE": 0}, 0
    for device_type, last_status in devices.type_and_status():
        total += 1
        group = VENDORS[device_type].group if device_type in VENDORS else "Other"
        vendors[group] = vendors.get(group, 0) + 1
        status[last_status if last_status in status else "NONE"] += 1
    values = scheduling.all_settings()
    db_info = database_info()
    health = {"disk": disk_health(), "database_bytes": db_info["bytes"],
              "database_engine": db_info["engine"] if show_internals else "Database",
              "database_name": db_info["name"] if show_internals else "",
              "backup_dir_exists": settings.BACKUP_DIR.is_dir(),
              "retention_months": scheduling.retention_months(),
              "syslog": syslog_receiver() if show_internals else None}
    return {"days": [{"d": k, **v} for k, v in per_day.items()], "ping": ping_history(), "status": status,
            "vendors": sorted(vendors.items(), key=lambda x: -x[1]), "total": total,
            "sched_on": values["sched_on"] == "1",
            "next_run": scheduling.next_scheduled_run(values),
            "ping_seconds": settings.PING_SECONDS, "job_running": backups.job_is_running(),
            "health": health, "last_job": last_job(), "attention": attention(), "changes": recent_changes(),
            "access": device_access() if show_internals else None,
            "ssh": active_sessions() if show_internals else None}
