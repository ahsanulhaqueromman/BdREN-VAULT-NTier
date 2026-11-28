"""RADIUS / AAA - read layer: RADIUS users, their devices, NAS clients, logins and admin events.

Reads the FreeRADIUS database (the `radius` connection, see repositories.py). Selectors never change data.
"""
import ipaddress
import logging
import re
from datetime import timedelta

from core.exceptions import ApiError

from database.radius.models import NO_DEVICE, ROLE_SUGGESTIONS, AuditLog, Nas, NasRole, RadCheck, RadUserGroup, UserDevice, UserGrant
from data_access.radius.repositories import DB

logger = logging.getLogger("dbms")
PASSWORD_ATTRS = ("Cleartext-Password", "SSHA2-256-Password", "NT-Password")
# rows that answer MS-CHAP / MS-CHAPv2 (MikroTik management logins); a user with neither needs the password set again
MSCHAP_ATTRS = ("Cleartext-Password", "NT-Password")
REJECTED_KEEP = timedelta(hours=24)   # rejected logins are shown, and kept, for this long only (accepted ones follow Settings)
LEGACY_ATTR = "NAS-IP-Address"
LEGACY_OP = "=~"


# ---- Recent device logins (Authentication Audit page) ----------------------------------------------
# FreeRADIUS's standard radpostauth table stores only username, reply and time - NOT the device the login
# came from. deploy/radius/enable_login_log.sh adds two columns (nasipaddress, nasidentifier) and makes
# FreeRADIUS fill them. Until it has run, logins are still listed, only without the device.
_LOGIN_COLS = {"at": 0.0, "cols": set(), "offset": 0}


def pattern_devices(value):
    """The IPv4 addresses inside a legacy "^(10[.]0[.]0[.]1|...)$" radcheck value; anything else gives []."""
    match = re.fullmatch(r"\^\((.*)\)\$", value or "")
    if not match:
        return []
    ips = [part.replace("[.]", ".") for part in match.group(1).split("|")]
    return ips if all(is_single_ip(ip) for ip in ips) else []


def is_single_ip(value):
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def user_devices():
    """{username: [ip, ...]}: the addresses FreeRADIUS lets each limited user log in on (dbms_user_nas)."""
    limits = {}
    for name, ip in UserDevice.objects.order_by("id").values_list("username", "nasname"):
        if ip != NO_DEVICE:
            limits.setdefault(name, []).append(ip)
        else:
            limits.setdefault(name, [])
    return limits


def user_grants():
    """{username: {"types": [...], "devices": [...]}}: what the administrator chose for each user.
    Users saved before device types existed have no grant rows; their dbms_user_nas addresses are
    their device grants (see access_of)."""
    grants = {}
    for name, kind, value in UserGrant.objects.order_by("id").values_list("username", "kind", "value"):
        g = grants.setdefault(name, {"types": [], "devices": []})
        g["types" if kind == UserGrant.TYPE else "devices"].append(value)
    return grants


def access_of(username, grants=None, limits=None):
    """{"types": [...], "devices": [...]} for one user; both empty = every device."""
    grants = user_grants() if grants is None else grants
    if username in grants:
        return grants[username]
    limits = user_devices() if limits is None else limits
    return {"types": [], "devices": list(limits.get(username, []))}


def usernames_with_type_grants():
    return sorted(set(UserGrant.objects.filter(kind=UserGrant.TYPE).values_list("username", flat=True)))


def nas_by_role():
    """{role in lower case: [single-address device, ...]}; a device with no role set counts as "Other"."""
    roles = roles_by_nasname()
    out = {}
    for nasname in Nas.objects.values_list("nasname", flat=True):
        if is_single_ip(nasname):
            out.setdefault(roles.get(nasname, "Other").lower(), []).append(nasname)
    return out


def user_exists(username):
    return RadCheck.objects.filter(username=username).exists()


def list_users(query=""):
    names = RadCheck.objects.filter(attribute__in=PASSWORD_ATTRS)
    if query:
        names = names.filter(username__icontains=query)
    names = sorted(set(names.values_list("username", flat=True)), key=str.lower)
    groups = dict(RadUserGroup.objects.values_list("username", "groupname"))
    limits, grants = user_devices(), user_grants()
    legacy = dict(RadCheck.objects.filter(attribute=LEGACY_ATTR, op=LEGACY_OP).values_list("username", "value"))
    mschap = set(RadCheck.objects.filter(attribute__in=MSCHAP_ATTRS).values_list("username", flat=True))
    out = []
    for n in names:
        access = access_of(n, grants, limits)
        out.append({"username": n, "level": groups.get(n, "-"), "types": access["types"],
                    "devices": access["devices"] or ([] if access["types"] else pattern_devices(legacy.get(n, ""))),
                    # every address the user can log in on right now (types expanded); [] with types = none yet
                    "effective": limits.get(n, []),
                    # False = stored before the NT hash was kept: MikroTik logins fail until the password is set again
                    "mschap": n in mschap})
    return out


def roles_by_nasname():
    """{nasname: role} for every NAS client that has a network role set."""
    return dict(NasRole.objects.values_list("nasname", "role"))


def distinct_roles():
    """Device-type suggestions for the drop-down: the built-in starting list plus any custom label an
    administrator has already typed in, so it is offered again instead of being retyped."""
    out, seen = list(ROLE_SUGGESTIONS), {r.lower() for r in ROLE_SUGGESTIONS}
    for role in sorted(set(NasRole.objects.values_list("role", flat=True)), key=str.lower):
        if role and role.lower() not in seen:           # "access switch" and "Access switch" are one type
            seen.add(role.lower())
            out.append(role)
    return out


def canonical_role(role):
    """The existing spelling of a device type when there is one (compared without case), otherwise the
    text as typed with a capital first letter - so one type never appears twice in different cases."""
    for known in distinct_roles():
        if known.lower() == role.lower():
            return known
    return role[:1].upper() + role[1:]


def selectable_devices():
    """Devices for the "Selected switches" list. Network entries (10.0.0.0/24) cannot be picked one by one."""
    roles = roles_by_nasname()
    return [{"name": d.shortname, "ip": d.nasname, "single": is_single_ip(d.nasname),
             "role": roles.get(d.nasname, "Other")}
            for d in Nas.objects.order_by("shortname")]


def _login_columns():
    import threading
    import time
    from django.db import connections
    lock = globals().setdefault("_LOGIN_COLS_LOCK", threading.Lock())
    with lock:
        if time.monotonic() - _LOGIN_COLS["at"] > 300:          # re-checked every 5 minutes (after running the script)
            conn = connections[DB]
            with conn.cursor() as cur:
                cols = {c.name.lower() for c in conn.introspection.get_table_description(cur, "radpostauth")}
                # FreeRADIUS writes authdate in the SERVER's local clock; MySQL NOW() uses the same clock,
                # so NOW() - UTC_TIMESTAMP() is the offset needed to show the right Bangladesh time.
                offset = 0
                try:
                    cur.execute("SELECT TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW())")
                    offset = int(cur.fetchone()[0] or 0)
                except Exception:
                    pass
            _LOGIN_COLS.update(at=time.monotonic(), cols=cols, offset=offset)
        return _LOGIN_COLS["cols"]


def device_namer(hostnames=None):
    """A function ip -> readable device name ("" when unknown), for labelling RADIUS logins.
    Looks in order: a NAS Clients entry for that exact address, a Device Inventory device with that address,
    `hostnames` ({ip: name}, e.g. the host name a device writes in its syslog messages), then a NAS Clients
    network entry (10.0.0.0/24) containing it - the smallest network wins.
    A NAS short name that is just the address again is skipped in favour of its description."""
    from data_access.devices import selectors as devices

    def label(short, desc, nasname):
        short, desc = (short or "").strip(), (desc or "").strip()
        if short and short != nasname and not is_single_ip(short):
            return short
        return desc if desc and not is_single_ip(desc) else ""

    exact, networks = {}, []
    for nasname, short, desc in Nas.objects.values_list("nasname", "shortname", "description"):
        name = label(short, desc, nasname)
        if not name:
            continue
        nasname = (nasname or "").strip()
        if is_single_ip(nasname):
            exact[nasname] = name
        else:
            try:
                networks.append((ipaddress.ip_network(nasname, strict=False), name))
            except ValueError:
                pass
    inventory = devices.names_by_ip()
    networks.sort(key=lambda n: -n[0].prefixlen)
    cache = {}

    def name_of(ip):
        ip = (ip or "").strip()
        if not ip:
            return ""
        if ip not in cache:
            found = exact.get(ip) or inventory.get(ip, "") or (hostnames or {}).get(ip, "")
            if not found:
                try:
                    addr = ipaddress.ip_address(ip)
                    found = next((n for net, n in networks if addr.version == net.version and addr in net), "")
                except ValueError:
                    found = ""
            cache[ip] = found
        return cache[ip]
    return name_of


def _db_clock(moment):
    """An aware datetime in the RADIUS database server's own clock (radpostauth.authdate is written in it)."""
    from datetime import timedelta, timezone as dt_tz
    return moment.astimezone(dt_tz.utc).replace(tzinfo=None) + timedelta(seconds=_LOGIN_COLS.get("offset", 0))


def recent_logins(q="", limit=20000, since=None, until=None, result=""):
    """Newest logins first: username, result, time and - when recorded - the device (IP, name).
    `q` matches the username, the device IP, or a device name from NAS Clients / Device Inventory;
    since / until (aware datetimes) limit it to a period; result "accept" / "reject" keeps only those logins
    (done in the query, so the newest `limit` are of that kind). Returns (rows, device_logging_enabled)."""
    from django.db import connections
    from data_access.devices import selectors as devices
    cols = _login_columns()
    has_ip, has_id, has_st = "nasipaddress" in cols, "nasidentifier" in cols, "calledstationid" in cols
    has_from = "callingstationid" in cols
    name_of = device_namer()
    names = dict(devices.names_by_ip())                         # device IP -> name, for searching by name
    for nasname, short in Nas.objects.values_list("nasname", "shortname"):
        if short and is_single_ip(nasname):
            names[nasname] = short
    where, params = [], []
    q = (q or "").strip()[:64]
    if q:
        ql = q.lower()
        parts, like = ["username LIKE %s"], f"%{q}%"
        params.append(like)
        if has_ip:
            parts.append("nasipaddress LIKE %s")
            params.append(like)
            ips = [ip for ip, n in names.items() if ql in n.lower()][:200]
            if ips:
                parts.append("nasipaddress IN (" + ",".join(["%s"] * len(ips)) + ")")
                params += ips
        if has_id:
            parts.append("nasidentifier LIKE %s")
            params.append(like)
        if has_st:
            parts.append("calledstationid LIKE %s")
            params.append(like)
        if has_from:
            parts.append("callingstationid LIKE %s")
            params.append(like)
        where.append("(" + " OR ".join(parts) + ")")
    if result == "accept":
        where.append("reply LIKE %s")
        params.append("%accept%")
    else:                                       # rejected ones only from the last 24 hours, even before the clean-up ran
        from datetime import datetime, timezone as _tz
        recent = _db_clock(datetime.now(_tz.utc) - REJECTED_KEEP)
        where.append("reply NOT LIKE %s AND authdate >= %s" if result == "reject" else "(reply LIKE %s OR authdate >= %s)")
        params += ["%accept%", recent]
    if since is not None:
        where.append("authdate >= %s")
        params.append(_db_clock(since))
    if until is not None:
        where.append("authdate < %s")
        params.append(_db_clock(until))
    sql = ("SELECT username, reply, authdate, " + ("nasipaddress" if has_ip else "''") + ", "
           + ("nasidentifier" if has_id else "''") + ", "
           + ("calledstationid" if has_st else "''") + ", "
           + ("callingstationid" if has_from else "''") + " FROM radpostauth"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT %s")
    params.append(max(1, min(int(limit), 20000)))
    with connections[DB].cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    from datetime import timedelta, timezone as dt_tz
    shift = timedelta(seconds=_LOGIN_COLS.get("offset", 0))
    as_utc = lambda t: (t - shift).replace(tzinfo=dt_tz.utc) if t is not None and t.tzinfo is None else t
    # name: NAS Clients / Device Inventory first, then the name the device itself sent (NAS-Identifier)
    out = [{"username": u, "reply": r or "", "authdate": as_utc(t), "nas_ip": ip or "", "nas_id": nid or "",
            "station": st or "", "from_ip": fr or "", "device": name_of(ip) or (nid or "")}
           for u, r, t, ip, nid, st, fr in rows]
    return out, has_ip


def accepted_logins(since, nas_ips, username="", limit=20000, until=None):
    """Successful logins (Access-Accept) since `since` (an aware datetime) on the given device addresses,
    oldest first: [(username, nas_ip, time in UTC)]. Used by Command History to know when a session began.
    [] when radpostauth does not record the device (enable_login_log.sh not run) or no address is given."""
    from datetime import timedelta, timezone as dt_tz
    from django.db import connections
    ips = sorted({ip for ip in nas_ips if ip})[:500]
    if not ips or "nasipaddress" not in _login_columns():
        return []
    shift = timedelta(seconds=_LOGIN_COLS.get("offset", 0))
    cutoff = since.astimezone(dt_tz.utc).replace(tzinfo=None) + shift
    sql = ("SELECT username, nasipaddress, authdate FROM radpostauth WHERE authdate >= %s AND reply = 'Access-Accept' "
           + ("AND authdate < %s " if until is not None else "")
           + "AND nasipaddress IN (" + ",".join(["%s"] * len(ips)) + ")" + (" AND username = %s" if username else "")
           + " ORDER BY authdate DESC LIMIT %s")
    params = ([cutoff] + ([_db_clock(until)] if until is not None else []) + [*ips]
              + ([username] if username else []) + [max(1, int(limit))])
    with connections[DB].cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out = []
    for u, ip, t in reversed(rows):
        if isinstance(t, str):                      # SQLite gives text
            from datetime import datetime
            try:
                t = datetime.fromisoformat(t)
            except ValueError:
                continue
        if t is not None and t.tzinfo is None:
            t = (t - shift).replace(tzinfo=dt_tz.utc)
        out.append((u, ip, t))
    return out


def accounting_stops(since, nas_ips, username="", limit=20000, until=None):
    """Logouts reported by RADIUS accounting (Accounting-Stop: radacct.acctstoptime) since `since` on the given
    device addresses, oldest first: [(username, nas_ip, time in UTC)]. Session Log uses them to close a session
    when the device does not send a logout message by syslog. [] when no address is given; raises
    DatabaseError when the radacct table is missing (the caller ignores it)."""
    from datetime import datetime, timedelta, timezone as dt_tz
    from django.db import connections
    ips = sorted({ip for ip in nas_ips if ip})[:500]
    if not ips:
        return []
    _login_columns()                                # finds the database clock offset (_LOGIN_COLS["offset"])
    shift = timedelta(seconds=_LOGIN_COLS.get("offset", 0))
    # a session that lasted some time: per-command accounting (Juniper interactive-commands, Cisco
    # "aaa accounting commands") writes Stop records of length 0, which are not logouts
    sql = ("SELECT username, nasipaddress, acctstoptime FROM radacct WHERE acctstoptime >= %s "
           "AND (acctsessiontime > 0 OR acctstoptime > acctstarttime) "
           + ("AND acctstoptime < %s " if until is not None else "")
           + "AND nasipaddress IN (" + ",".join(["%s"] * len(ips)) + ")" + (" AND username = %s" if username else "")
           + " ORDER BY acctstoptime DESC LIMIT %s")
    params = ([_db_clock(since)] + ([_db_clock(until)] if until is not None else []) + [*ips]
              + ([username] if username else []) + [max(1, int(limit))])
    with connections[DB].cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out = []
    for u, ip, t in reversed(rows):
        if isinstance(t, str):                      # SQLite gives text
            try:
                t = datetime.fromisoformat(t)
            except ValueError:
                continue
        if t is None:
            continue
        if t.tzinfo is None:
            t = (t - shift).replace(tzinfo=dt_tz.utc)
        out.append((u, ip, t))
    return out


SUMMARY_WINDOWS = (24, 24 * 7, 24 * 30, 24 * 90, 24 * 365)   # = core.period.PRESETS


def login_summary(hours=24, since=None, until=None):
    """What happened in the last `hours` (or from `since` to `until`, aware datetimes): attempts, accepted /
    rejected, how many different users and devices.

    radpostauth.authdate is written in the database server's own clock, so the cutoff is computed in that
    clock (the offset found by _login_columns()). Uses the dbms_authdate index created by radius_init."""
    from datetime import datetime, timedelta, timezone as dt_tz
    from django.db import connections
    hours = hours if hours in SUMMARY_WINDOWS else 24
    cols = _login_columns()
    has_ip = "nasipaddress" in cols
    if since is None:
        since = datetime.now(dt_tz.utc) - timedelta(hours=hours)
    where, params = "authdate >= %s", [_db_clock(since)]
    if until is not None:
        where, params = where + " AND authdate < %s", params + [_db_clock(until)]
    where += " AND (reply = 'Access-Accept' OR authdate >= %s)"      # failed logins exist for 24 hours only
    params.append(_db_clock(datetime.now(dt_tz.utc) - REJECTED_KEEP))
    device_count = ("COUNT(DISTINCT CASE WHEN nasipaddress <> '' THEN nasipaddress END)" if has_ip else "0")
    with connections[DB].cursor() as cur:
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN reply = 'Access-Accept' THEN 1 ELSE 0 END), "
                    "COUNT(DISTINCT username), " + device_count + " FROM radpostauth WHERE " + where, params)
        total, accepted, users, devices_n = cur.fetchone()
    total, accepted = int(total or 0), int(accepted or 0)
    return {"hours": hours, "total": total, "accepted": accepted, "rejected": total - accepted,
            "users": int(users or 0), "devices": int(devices_n or 0), "device_logging": has_ip}


def limit_violations(hours=24):
    """Logins FreeRADIUS ACCEPTED on a device outside the user's allowed list, in the last `hours`.
    Any row means the per-device limit is not enforced (dbms_device_limit policy missing from
    authorize { }) or a switch sends its requests from an address that is not the one in NAS Clients.
    Needs the device columns of radpostauth (deploy/radius/enable_login_log.sh); [] without them."""
    from django.db import connections
    try:
        if "nasipaddress" not in _login_columns():
            return []
        sql = ("SELECT p.username, p.nasipaddress, MAX(p.authdate), COUNT(*) FROM radpostauth p "
               "WHERE p.reply = 'Access-Accept' AND p.nasipaddress <> '' "
               "AND p.authdate >= NOW() - INTERVAL %s HOUR "
               "AND EXISTS (SELECT 1 FROM dbms_user_nas a WHERE a.username = p.username) "
               "AND NOT EXISTS (SELECT 1 FROM dbms_user_nas d WHERE d.username = p.username AND d.nasname = p.nasipaddress) "
               "GROUP BY p.username, p.nasipaddress "
               # already fixed: FreeRADIUS has REFUSED this user on this device after the last accepted login
               "HAVING MAX(p.id) > COALESCE((SELECT MAX(r.id) FROM radpostauth r WHERE r.username = p.username "
               "AND r.nasipaddress = p.nasipaddress AND r.reply = 'Access-Reject'), 0) "
               "ORDER BY MAX(p.authdate) DESC LIMIT 20")
        with connections[DB].cursor() as cur:
            cur.execute(sql, [int(hours)])
            rows = cur.fetchall()
    except Exception:
        logger.warning("Could not check per-device login limits", exc_info=True)
        return []
    # a login accepted BEFORE the user's devices were last changed was allowed then (e.g. "All devices"
    # until an hour ago): only a login after the change can break the current limit
    changed = _last_user_change({u for u, _, _, _ in rows})
    rows = [r for r in rows if not _before(r[2], changed.get(r[0]))]
    name_of = device_namer()
    return [{"username": u, "ip": ip, "device": name_of(ip), "count": n,
             "last": t.strftime("%d %b %Y, %I:%M %p") if hasattr(t, "strftime") else str(t or "")}
            for u, ip, t, n in rows]


def _last_user_change(usernames):
    """{username: when the user was last created or edited (RADIUS admin log), in the database clock}."""
    from django.db.models import Max
    if not usernames:
        return {}
    rows = (AuditLog.objects.filter(action__in=("user.create", "user.update"), target__in=usernames)
            .values("target").annotate(at=Max("created_at")))
    return {r["target"]: _db_clock(r["at"]) for r in rows if r["at"]}


def _before(login_at, changed_at):
    if changed_at is None or not hasattr(login_at, "tzinfo"):
        return False
    if login_at.tzinfo is not None:                  # raw cursors normally give the database clock, naive
        login_at = _db_clock(login_at)
    return login_at < changed_at


def nas_rows():
    """NAS Clients list. Shared secrets are NOT included: one is sent only when asked for (get_nas)."""
    roles = roles_by_nasname()
    return [{"id": d.pk, "name": d.shortname, "nasname": d.nasname, "vendor": d.type,
             "role": roles.get(d.nasname, "Other"), "description": d.description or ""}
            for d in Nas.objects.order_by("shortname")]


def nas_addresses():
    """[(address or network, vendor type)] of every NAS Clients entry, for the syslog receiver's allow-list."""
    return [((n or "").strip(), t or "") for n, t in Nas.objects.values_list("nasname", "type")]


def get_nas(pk):
    device = Nas.objects.filter(pk=pk).first()
    if device is None:
        raise ApiError(404, "Device not found")
    return device


def nas_exists(nasname):
    return Nas.objects.filter(nasname=nasname).exists()


def admin_events(limit=500):
    """Changes made on the RADIUS pages, newest first (shown in Activity Logs > Administrative audit trail)."""
    return AuditLog.objects.all()[:limit]
