"""Turn one syslog message from a network device into a command-history event, or None.

Pure text work (no database): every vendor writes "who did what" in its own format, so each parser looks for
its own marker and returns a dict:

    {"vendor": "huawei", "kind": "command", "username": "shamim", "source_ip": "10.0.0.5",
     "command": "display interface brief", "result": ""}

kind is one of KINDS. A message that is not about a user (link up/down, OSPF, ...) returns None and is only
counted. Device-side settings that make each vendor send these lines: Device Setup > Command logging.
"""
import re

KINDS = ("command", "change", "login", "logout", "login-failed")
MAX_COMMAND = 1000

# Commands that only look or move between modes; everything else is counted as a change.
READ_ONLY = re.compile(
    r"^(?:dis(?:p(?:l(?:a(?:y)?)?)?)?|sh(?:o(?:w)?)?|ping|tracert|traceroute|trace|screen-length|terminal|"
    r"quit|q|return|exit|end|system-view|sys|configure|conf(?:ig(?:ure)?)?(?:\s+t(?:erminal)?)?|enable|en|"
    r"undo\s+terminal|monitor|top|super|clock\s+show|dir|more|less|cd|pwd|help|\?|history|"
    r"/?\s*(?:print|export|monitor)|request\s+system\s+(?:storage|information)|file\s+show)\b",
    re.I)
# Commands that only enter a mode when typed on their own (Huawei "diagnose" opens the diagnostic view);
# with more words after them they can do something, so only the bare command is read-only.
MODE_ONLY = re.compile(r"^diag(?:n(?:o(?:s(?:e)?)?)?)?$", re.I)


def is_change(command):
    """True when a CLI command may change the device (anything that is not a show / ping / mode switch).
    Cisco "do <command>" runs an exec command from configuration mode, so "do show run" is read-only."""
    text = re.sub(r"^do\s+", "", (command or "").strip(), flags=re.I)
    return bool(text) and not READ_ONLY.match(text) and not MODE_ONLY.match(text)


# ---- the device's host name, from the syslog header ----------------------------------------------------------
# <189>Nov 24 2026 11:19:00 Training-Room-AS-04 %%01SHELL/5/CMDRECORD...     (Huawei)
# <189>Nov 24 11:19:00 core-rtr mgd[1234]: UI_CMDLINE_READ_LINE...            (Juniper, RFC 3164)
# <189>1 2026-11-24T11:19:00+06:00 core-rtr mgd 1234 UI_LOGIN_EVENT ...      (RFC 5424)
# ... devname="FGT-01" ...                                                     (Fortinet)
# Cisco writes its name only with "logging origin-id hostname" (_CISCO_HOST); without it the address is shown.
_TS = (r"(?:[A-Z][a-z]{2}\s+\d{1,2}(?:\s+\d{4})?\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?"
       r"|\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)(?:Z|[+-]\d{2}:?\d{2})?")
_HOST = re.compile(r"^<\d{1,3}>(?:1 )?" + _TS + r"\s+([A-Za-z0-9][A-Za-z0-9._-]{0,63})\s")
_FORTI_HOST = re.compile(r'\bdevname="?([A-Za-z0-9][A-Za-z0-9._-]{0,63})')
# Cisco with "logging origin-id hostname": <189>812: SUST-EDGE-R1: *Nov 24 12:41:13.080 BST: %SYS-5-CONFIG_I: ...
# (the sequence number is optional; the name starts with a letter, so a number is never taken for it)
_CISCO_HOST = re.compile(r"^<\d{1,3}>(?:\d+:\s*)?([A-Za-z][A-Za-z0-9._-]{0,63}):\s+(?:\d+:\s+)?[*.]?[A-Z][a-z]{2}\s+\d")


def hostname(data):
    """The host name in a syslog message's header, or "" (none written, or only an address)."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else (data or "")
    m = _HOST.match(text) or _CISCO_HOST.match(text) or _FORTI_HOST.search(text)
    if not m:
        return ""
    name = m.group(1)
    if re.fullmatch(r"[\d.]+", name):              # only an IPv4 address: the address is shown anyway
        return ""
    return name


def _clean(value, limit=MAX_COMMAND):
    value = re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]", " ", value or "").strip()
    return value[:limit]


def _event(vendor, kind, username, command="", source_ip="", result=""):
    import ipaddress
    username = _clean(username, 64).strip("'\"")
    if not username:
        return None
    cleaned_ip = _clean(source_ip, 64)
    if set(cleaned_ip or "") <= {"*", " "}:           # Huawei writes Ip=** when it hides the address
        cleaned_ip = ""
    elif cleaned_ip:
        try:
            cleaned_ip = str(ipaddress.ip_address(cleaned_ip))
        except ValueError:
            cleaned_ip = ""
    return {"vendor": vendor, "kind": kind, "username": username, "source_ip": cleaned_ip,
            "command": _clean(command), "result": _clean(result, 32)}


# ---- Huawei VRP 5 / VRP 8 ----------------------------------------------------------------------------------
# SHELL/5/CMDRECORD(s)[3]:Recorded command information. (Task=VT0, Ip=10.0.0.5, VpnName=, User=shamim,
#   AuthenticationMethod="RADIUS", Command="display interface brief", Result=Success)
# SSH/5/SSH_USER_LOGIN(l): The SSH user succeeded in logging in. (UserName=shamim, IPAddress=10.0.0.5, ...)
_HW_TAG = re.compile(r"(?:%%\d*|\b)([A-Z][A-Z0-9_]+)/\d/([A-Z][A-Z0-9_]+)")
_HW_KV = re.compile(r'([A-Za-z][A-Za-z0-9_]*)=("(?:[^"\\]|\\.)*"|[^,)]*)')


def _hw_fields(text):
    m = re.search(r"\((?=\s*[A-Za-z_]+=)", text)        # the "(Key=value, ...)" part
    body = text[m.end():] if m else text
    return {k.lower(): v.strip().strip('"').rstrip(".") for k, v in _HW_KV.findall(body)}


def huawei(text):
    m = _HW_TAG.search(text)
    if not m:
        return None
    module, name = m.group(1), m.group(2)
    f = _hw_fields(text[m.end():])
    user = f.get("user") or f.get("username") or f.get("user_name") or ""
    ip = f.get("ip") or f.get("ipaddress") or f.get("useraddress") or f.get("ipaddr") or ""
    if name == "CMDRECORD":
        command = f.get("command", "")
        result = f.get("result", "")
        return _event("huawei", "change" if is_change(command) else "command", user, command, ip, result)
    if "LOGIN" in name or "LOGOUT" in name or module in ("SSH", "TELNET") and "USER" in name:
        if "FAIL" in name:
            kind = "login-failed"
        elif "LOGOUT" in name or "OFFLINE" in name:
            kind = "logout"
        else:
            kind = "login"
        how = module.lower() if module in ("SSH", "TELNET", "FTPS", "SFTP", "HTTP") else ""
        return _event("huawei", kind, user, how, ip)
    return None


# ---- Cisco IOS / IOS-XE (also BDCOM, which copies the Cisco messages on many firmwares) ----------------------
# %PARSER-5-CFGLOG_LOGGEDCMD: User:shamim  logged command:interface GigabitEthernet0/1
# %SEC_LOGIN-5-LOGIN_SUCCESS: Login Success [user: shamim] [Source: 10.0.0.5] [localport: 22] at ...
# %SEC_LOGIN-4-LOGIN_FAILED: Login failed [user: x] [Source: 10.0.0.5] [localport: 22] [Reason: ...] at ...
# %SYS-5-CONFIG_I: Configured from console by shamim on vty0 (10.0.0.5)
_CISCO_CMD = re.compile(r"%PARSER-\d-CFGLOG_LOGGEDCMD:\s*User:\s*(\S+)\s+logged command:\s*(.*)$", re.I)
_CISCO_LOGIN = re.compile(r"%SEC_LOGIN-\d-(LOGIN_SUCCESS|LOGIN_FAILED|LOGOUT)\b.*?\[user:\s*([^\]]*)\]"
                          r"(?:.*?\[Source:\s*([^\]]*)\])?", re.I)
# Show / exec commands, sent by the EEM applet of Device Setup (Cisco logs configuration commands only):
# %HA_EM-5-LOG: VAULT-CLI-LOG: user=shamim cmd=show running-config
_CISCO_EEM = re.compile(r"%HA_EM-\d-LOG:\s*VAULT-CLI-LOG:\s*user=(\S*)\s+cmd=(.*)$", re.I)
# end / exit / quit already show up from the archive log ("configuration finished", exit), so the applet's copy
# is left out; configure terminal is not logged by the archive, so it is kept
_CISCO_MODE = re.compile(r"^(?:end|exit|quit)$", re.I)
# End of a session, sent by IOS as soon as it closes (quit / exit, or the window or connection just dropped):
# %SSH-5-SSH2_CLOSE: SSH2 Session from 10.0.0.5 (tty = 0) for user 'shamim' using crypto cipher 'aes128-ctr' ... closed
# %SYS-6-LOGOUT: User shamim has exited tty session 2(10.0.0.5)      (level 6: needs "logging trap informational")
_CISCO_SSH_CLOSE = re.compile(r"%SSH-\d-SSH2_CLOSE:\s*SSH2 Session from\s+(\S+).*?for user\s+'([^']*)'", re.I)
_CISCO_EXIT = re.compile(r"%SYS-\d-LOGOUT:\s*User\s+(\S+)\s+has exited tty session\s+\d+(?:\(([^)]*)\))?", re.I)
_CISCO_CONFIG = re.compile(r"%SYS-\d-CONFIG_I:\s*Configured from (\S+) by (\S+)(?:\s+on\s+\S+)?(?:\s*\(([^)]*)\))?",
                           re.I)


def cisco(text):
    m = _CISCO_EEM.search(text)
    if m:
        user, command = m.group(1), m.group(2).strip()
        if user.startswith("$") or is_change(command) or _CISCO_MODE.match(command):
            # $_cli_username not known on this IOS; changes are logged by the archive (CFGLOG) message already;
            # end / exit / quit are already in the log from the archive (see _CISCO_MODE)
            return None
        return _event("cisco", "command", user, command)
    m = _CISCO_CMD.search(text)
    if m:
        command = m.group(2)
        return _event("cisco", "change" if is_change(command) else "command", m.group(1), command)
    m = _CISCO_LOGIN.search(text)
    if m:
        kind = {"LOGIN_SUCCESS": "login", "LOGIN_FAILED": "login-failed", "LOGOUT": "logout"}[m.group(1).upper()]
        return _event("cisco", kind, m.group(2), "", m.group(3) or "")
    m = _CISCO_SSH_CLOSE.search(text)
    if m and m.group(2):
        return _event("cisco", "logout", m.group(2), "", m.group(1))
    m = _CISCO_EXIT.search(text)
    if m:
        return _event("cisco", "logout", m.group(1), "", m.group(2) or "")
    m = _CISCO_CONFIG.search(text)
    if m:
        return _event("cisco", "change", m.group(2), f"configuration finished (from {m.group(1)})", m.group(3) or "")
    return None


# ---- Juniper Junos ---------------------------------------------------------------------------------------------
# UI_CMDLINE_READ_LINE: User 'shamim', command 'show interfaces terse '
# UI_COMMIT: User 'shamim' requested 'commit' operation (comment: none)
# UI_CFG_AUDIT_SET: User 'shamim' set: [interfaces ge-0/0/0 description] <unconfigured> -> "uplink"
# UI_LOGIN_EVENT: User 'shamim' login, class 'j-super-user' [1234], ssh-connection '10.0.0.5 51234 10.0.0.1 22'
# UI_LOGOUT_EVENT: User 'shamim' logout
_JUN = re.compile(r"\b(UI_[A-Z_]+):\s*User '([^']*)'(.*)$")


def juniper(text):
    m = _JUN.search(text)
    if not m:
        return None
    tag, user, rest = m.groups()
    if tag == "UI_CMDLINE_READ_LINE":
        c = re.search(r"command '(.*)'\s*$", rest)
        command = c.group(1) if c else ""
        return _event("juniper", "change" if is_change(command) else "command", user, command)
    if tag in ("UI_COMMIT", "UI_COMMIT_CONFIRMED"):
        c = re.search(r"requested '([^']*)' operation(.*)$", rest)
        return _event("juniper", "change", user, (c.group(1) + c.group(2)).strip() if c else "commit")
    if tag.startswith("UI_CFG_AUDIT"):
        return _event("juniper", "change", user, rest.lstrip(" ,:"))
    if tag == "UI_LOGIN_EVENT":
        c = re.search(r"-connection '(\S+)", rest)
        return _event("juniper", "login", user, "", c.group(1) if c else "")
    if tag == "UI_LOGOUT_EVENT":
        return _event("juniper", "logout", user)
    if tag == "UI_AUTH_EVENT" and "fail" in rest.lower():
        return _event("juniper", "login-failed", user)
    return None


# ---- MikroTik RouterOS -----------------------------------------------------------------------------------------
# user shamim logged in from 10.0.0.5 via ssh          user shamim logged out from 10.0.0.5 via ssh
# login failure for user x from 10.0.0.5 via ssh
# ip address added by ssh:shamim@10.0.0.5 (*5 = /ip address add address=10.1.1.1/24 interface=ether2)
# interface ether1 changed by winbox-3.40/tcp-msg(winbox):shamim@10.0.0.5 (/interface set ether1 disabled=yes)
_MT_LOGIN = re.compile(r"\buser (\S+) logged (in|out) from (\S+)(?: via (\S+))?", re.I)
_MT_FAIL = re.compile(r"\blogin failure for user (\S+) from (\S+)(?: via (\S+))?", re.I)
_MT_CHANGE = re.compile(r"^(\S.*?) (added|changed|removed|moved) by (\S+)(?: \((.*)\))?\s*$")
# what comes before the message itself: "Nov 23 10:41:05 MikroTik " and the topics "system,info,account "
_MT_HEAD = re.compile(r"^(?:[A-Z][a-z]{2}\s+\d{1,2}\s+\d\d:\d\d:\d\d\s+\S+\s+)?(?:[a-z]+(?:,[a-z]+)+:?\s+)?")


def mikrotik(text):
    m = _MT_LOGIN.search(text)
    if m:
        return _event("mikrotik", "login" if m.group(2).lower() == "in" else "logout", m.group(1), m.group(4) or "",
                      m.group(3))
    m = _MT_FAIL.search(text)
    if m:
        return _event("mikrotik", "login-failed", m.group(1), m.group(3) or "", m.group(2))
    m = _MT_CHANGE.search(_MT_HEAD.sub("", text, count=1))
    if m:
        what, verb, by, detail = m.groups()
        who = by.rsplit(":", 1)[-1]
        user, _, ip = who.partition("@")
        if not user or "/" in user:
            return None
        command = re.sub(r"^\*[0-9A-Fa-f]+\s*=\s*", "", detail or "") or f"{what} {verb}"
        return _event("mikrotik", "change", user, command, ip)
    return None


# ---- Fortinet FortiGate / FortiSwitch (key=value event logs) ------------------------------------------------------
# logid="0100044547" type="event" subtype="system" user="shamim" ui="ssh(10.0.0.5)" action="Edit"
#   cfgpath="system.interface" cfgobj="port1" cfgattr="alias[->wan]" msg="Edit system.interface port1"
# FortiSwitch: log_id=0103023811 ... user="admin" ui="GUI(192.168.99.132)" action=edit cfg_path="router.static" cfg_obj="1"
# logid="0100032001" ... user="shamim" ui="ssh(10.0.0.5)" action="login" status="success" msg="Administrator ..."
_FORTI_KV = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')


def fortinet(text):
    # FortiGate writes logid= / cfgpath= / cfgobj= / cfgattr=; FortiSwitch writes log_id= / cfg_path= / cfg_obj= / cfg_attr=
    if ("logid=" not in text and "log_id=" not in text) or "user=" not in text:
        return None
    f = {k.replace("_", ""): v.strip('"') for k, v in _FORTI_KV.findall(text)}
    user, action = f.get("user", ""), f.get("action", "").lower()
    ui = f.get("ui", "")
    ip_m = re.search(r"\(([^)]*)\)", ui)
    ip = ip_m.group(1) if ip_m else f.get("srcip", "")
    how = ui.split("(")[0]
    if action == "login":
        return _event("fortinet", "login" if f.get("status", "").lower() == "success" else "login-failed", user,
                      how, ip)
    if action == "logout":
        return _event("fortinet", "logout", user, how, ip)
    if f.get("cfgpath"):
        parts = [f.get("action", ""), f.get("cfgpath", ""), f.get("cfgobj", ""), f.get("cfgattr", "")]
        return _event("fortinet", "change", user, " ".join(p for p in parts if p), ip)
    return None


PARSERS = {"huawei": huawei, "cisco": cisco, "juniper": juniper, "fortinet": fortinet, "mikrotik": mikrotik}
# NAS Clients vendor -> the parser tried first for messages from that device
HINTS = {"huawei": "huawei", "huawei-3": "huawei", "cisco": "cisco", "bdcom": "cisco", "juniper": "juniper",
         "fortinet": "fortinet", "mikrotik": "mikrotik"}
_PRI = re.compile(r"^\s*<\d{1,3}>\s*(?:1\s)?")


def parse(message, vendor=""):
    """One syslog message (bytes or str) -> event dict, or None when it is not about a user's action.
    vendor (the NAS Clients type of the sender, optional) picks the parser that is tried first."""
    if isinstance(message, bytes):
        message = message.decode("utf-8", "replace")
    text = _PRI.sub("", message).strip()
    if not text:
        return None
    first = PARSERS.get(HINTS.get(vendor, ""))
    candidates = [first] if first is not None else list(PARSERS.values())
    for parser in candidates:
        try:
            event = parser(text)
        except Exception:          # a strange message must never stop the receiver
            event = None
        if event:
            return event
    return None
