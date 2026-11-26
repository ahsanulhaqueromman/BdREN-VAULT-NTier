"""Configuration change report: what changed on every device in the last 1, 3, 6 or 12 months.

Only CHANGED configurations are saved as files (unchanged runs write no file), so every saved version
inside the period is one configuration change. Each change is compared with the version before it -
for the first change in the period that is the last version saved BEFORE the period ("baseline").
Volatile lines (timestamps, "Building configuration ..." and similar) are ignored, exactly as when
a backup decides whether a configuration changed (services.normalize).
"""
import difflib
import re
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from django.utils import timezone

from apps.devices.selectors import device_selectors as devices

from apps.backups.repositories import backup_storage as storage
from apps.backups.services.backup_service import normalize

PERIODS = {1: 30, 3: 91, 6: 182, 12: 365}       # months -> days
PREVIEW_LINES = 8                               # changed lines shown per change in the report
MAX_CHANGES = 200                               # per device, newest kept


_STAMP = re.compile(r"_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$")


def _when(path):
    """Snapshot time from its file name (device_YYYYMMDD_HHMMSS.txt), else the file time."""
    return _when_of(str(path))


@lru_cache(maxsize=400000)           # saved snapshots never change; a 20,000-device report reuses the results
def _when_of(path):
    path = Path(path)
    m = _STAMP.search(path.stem)
    tz = timezone.get_current_timezone()
    if m:
        try:
            return datetime(*map(int, m.groups())).replace(tzinfo=tz)
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=tz)


def _compare(old_text, new_text):
    """(lines added, lines removed, short preview of the changed lines)."""
    old_lines, new_lines = normalize(old_text).splitlines(), normalize(new_text).splitlines()
    added = removed = 0
    preview = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=0):
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
        else:
            continue
        if len(preview) < PREVIEW_LINES and line[1:].strip():
            preview.append(line[0] + " " + line[1:].strip()[:160])
    return added, removed, preview


def month_range(from_month, to_month):
    """("2026-01", "2026-03") -> (1 Jan 2026 00:00, 31 Mar 2026 23:59:59) in local time; raises ValueError."""
    tz = timezone.get_current_timezone()
    start = datetime.strptime(from_month, "%Y-%m").replace(tzinfo=tz)
    last = datetime.strptime(to_month, "%Y-%m").replace(tzinfo=tz)
    nxt = last.replace(year=last.year + 1, month=1) if last.month == 12 else last.replace(month=last.month + 1)
    end = nxt - timedelta(seconds=1)
    if end < start:
        raise ValueError("The end month is before the start month")
    return start, end


# Saved backups never change once written, so a comparison is cached by (file, modification time).
# With 500-1000 devices the first report reads the files once; later reports reuse the results.
@lru_cache(maxsize=100000)
def _compare_files(old_path, old_mtime, new_path, new_mtime):
    added, removed, preview = _compare(Path(old_path).read_text(encoding="utf-8", errors="replace"),
                                       Path(new_path).read_text(encoding="utf-8", errors="replace"))
    return added, removed, tuple(preview)


@lru_cache(maxsize=100000)
def _line_count(path, mtime):
    return len(normalize(Path(path).read_text(encoding="utf-8", errors="replace")).splitlines())


def change_report(months=None, start=None, end=None):
    """Changes in the last `months` (1, 3, 6, 12), or between `start` and `end` (a chosen month range)."""
    now = timezone.localtime()
    if start is None:
        start = now - timedelta(days=PERIODS[months])
    end = min(end or now, now)
    devices_by_key = {}
    for d in devices.devices_by_id():
        for key in (d.name, d.ip, d.ip.replace(".", "_")):
            if key:
                devices_by_key.setdefault(storage.safe_name(key).lower(), d)

    rows = []
    for folder, stamp in storage.device_folders():
        part = _device_part(folder, stamp, start, end)
        if part is None:
            continue
        device = devices_by_key.get(folder.name.lower())
        # Fresh dicts every call: the cached part is shared, and the view blanks previews for Viewers.
        rows.append({**part, "device_id": device.pk if device else None, "ip": device.ip if device else "",
                     "type": device.device_type if device else "", "timeline": [dict(c) for c in part["timeline"]]})
    rows.sort(key=lambda r: (-r["changes"], r["last_change"] == "", r["device"].lower()))
    changed = [r for r in rows if r["changes"]]
    return {
        "months": months, "from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d"),
        "summary": {"devices": len(rows), "changed": len(changed), "unchanged": len(rows) - len(changed),
                    "changes": sum(r["changes"] for r in rows), "added": sum(r["added"] for r in rows),
                    "removed": sum(r["removed"] for r in rows)},
        "devices": rows,
    }


# One device's part of the report, kept until that device gets a new backup (its folder time changes) or the
# period moves past one of its versions. With thousands of devices a report then only re-reads the devices
# that changed; the rest is a dictionary look-up. Device name / IP / type are added fresh on every call.
_PARTS = {}          # folder name -> (folder stamp, files, times, key, part)
_PARTS_LOCK = threading.Lock()


def _device_part(folder, stamp, start, end):
    with _PARTS_LOCK:
        hit = _PARTS.get(folder.name)
    if hit and hit[0] == stamp:
        files, times = hit[1], hit[2]
    else:
        files = storage.versions(folder, stamp)          # from the version index, not a walk of the disk
        times = [_when(f) for f in files]
        hit = None
    # Which versions are before / inside the period decides the result, so that is the cache key.
    dated = [i for i, t in enumerate(times) if t <= end]          # versions saved after the range are ignored
    before = [i for i in dated if times[i] < start]
    inside = tuple(i for i in dated if times[i] >= start)
    key = (before[-1] if before else -1, inside, dated[-1] if dated else -1)
    if hit and hit[3] == key:
        return hit[4]
    part = _build_part(folder, files, times, dated, before, inside)
    with _PARTS_LOCK:
        _PARTS[folder.name] = (stamp, files, times, key, part)
    return part


def _build_part(folder, files, times, dated, before, inside):
    if not dated:
        return None
    cut = len(str(folder)) + 1

    def rel(path):
        return str(path)[cut:].replace("\\", "/")
    prev = files[before[-1]] if before else None
    changes = []
    for i in inside:
        f, t = files[i], times[i]
        entry = {"file": rel(f), "time": t.strftime("%Y-%m-%d %H:%M:%S"), "prev": rel(prev) if prev else ""}
        if prev is None:
            entry.update(first=True, added=_line_count(str(f), f.stat().st_mtime_ns), removed=0, preview=[])
        else:
            added, removed, preview = _compare_files(str(prev), prev.stat().st_mtime_ns, str(f), f.stat().st_mtime_ns)
            if not added and not removed:
                # Saved only because a clock / "last change" line differed (older builds, e.g. IOS XR):
                # not a real change, so it is left out and the next version compares with the same base.
                continue
            entry.update(first=False, added=added, removed=removed, preview=list(preview))
        changes.append(entry)
        prev = f
    real = [c for c in changes if not c["first"]]
    return {
        "device": folder.name,
        "changes": len(real),
        "first_backup_in_period": any(c["first"] for c in changes),
        "added": sum(c["added"] for c in real),
        "removed": sum(c["removed"] for c in real),
        "last_change": changes[-1]["time"] if changes else "",
        "baseline": rel(files[before[-1]]) if before else "",
        "latest": rel(files[dated[-1]]),        # newest version inside the range
        "timeline": list(reversed(changes))[:MAX_CHANGES],          # newest first
    }
