"""Writes for Command History: what the syslog receiver hands over, and the daily clean-up."""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.radius import services as radius
from apps.scheduling.services import retention_cutoff

from apps.commandlog.models import CommandEvent, ReceiverState, SyslogSource
from apps.commandlog.selectors import REJECTED_FOR

logger = logging.getLogger("dbms")

_named = set()   # (ip, hostname) already offered to NAS Clients by this receiver process


def record(events, stats, now=None):
    """Save one batch from the receiver.
    events: [{"device_ip", "username", "kind", ...}]   stats: {ip: {"received": n, "recognized": n, "sample": str}}"""
    now = now or timezone.now()
    with transaction.atomic():
        if events:
            CommandEvent.objects.bulk_create([CommandEvent(received_at=e.get("at", now), device_ip=e["device_ip"],
                                                           username=e["username"], source_ip=e["source_ip"],
                                                           kind=e["kind"], command=e["command"],
                                                           result=e["result"], vendor=e["vendor"])
                                              for e in events], batch_size=500)
        for ip, s in stats.items():
            source, _ = SyslogSource.objects.get_or_create(ip=ip, defaults={"first_seen": now, "last_seen": now})
            changes = {"last_seen": now, "received": F("received") + s["received"],
                       "recognized": F("recognized") + s["recognized"]}
            if s.get("sample"):
                changes["last_unrecognized"] = s["sample"][:500]
            if s.get("hostname"):
                changes["hostname"] = s["hostname"][:64]
            SyslogSource.objects.filter(pk=source.pk).update(**changes)
    for ip, s in stats.items():   # a NAS entry added without a name gets the device's own name
        key = (ip, s.get("hostname") or "")
        if key[1] and key not in _named:
            _named.add(key)
            try:
                radius.name_nas_from_syslog(*key)
            except Exception:
                logger.exception("Could not name NAS Clients entry %s from its syslog", ip)


def heartbeat(port, rejected=0, rejected_ip="", dropped=0, started=False, now=None):
    """The receiver is alive; add the messages it refused since the last heartbeat."""
    now = now or timezone.now()
    row, _ = ReceiverState.objects.get_or_create(pk=1)
    changes = {"heartbeat": now, "port": port, "dropped": F("dropped") + dropped}
    if rejected:
        # count refused messages per spell: after a quiet day the count starts again (see selectors.REJECTED_FOR)
        fresh = row.rejected_at is None or now - row.rejected_at > REJECTED_FOR
        changes.update(rejected=rejected if fresh else F("rejected") + rejected, rejected_at=now)
    if started:
        changes["started_at"] = now
    if rejected_ip:
        changes["rejected_last_ip"] = rejected_ip[:45]
    ReceiverState.objects.filter(pk=1).update(**changes)


DISMISSABLE = {   # Session Log notes an administrator may clear; each comes back with the next such message
    "rejected": {"rejected": 0, "rejected_last_ip": "", "rejected_at": None},   # "log messages were ignored"
    "dropped": {"dropped": 0},                                                   # "messages were dropped"
}


def dismiss_note(note):
    """Clear one Session Log note (a key of DISMISSABLE). Returns False for an unknown note."""
    if note not in DISMISSABLE:
        return False
    ReceiverState.objects.filter(pk=1).update(**DISMISSABLE[note])
    return True


def prune_old_events(now=None):
    """Delete Session Log events (logins, commands, changes) older than Settings > "Keep logs and backup files
    for" (Forever = keep all). Runs once a day from the background threads. Returns the number of rows removed."""
    cutoff = retention_cutoff(now)
    if cutoff is None:
        return 0
    removed = 0
    while True:                       # in slices, so a large table never locks for long
        ids = list(CommandEvent.objects.filter(received_at__lt=cutoff).values_list("id", flat=True)[:5000])
        if not ids:
            break
        removed += CommandEvent.objects.filter(id__in=ids).delete()[0]
    if removed:
        logger.info("Session Log: removed %s entries older than the retention period", removed)
    return removed
