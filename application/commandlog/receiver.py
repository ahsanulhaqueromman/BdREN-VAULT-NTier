"""The syslog receiver: listens on UDP (514 by default) and keeps what users did on the network devices.

Run by `manage.py syslog_receive` (systemd unit deploy/systemd/vault-syslog.service), in its own process so the web
server never needs the privileged port. Rules:

  * only addresses on NAS Clients (single addresses or networks) are accepted;
    every other message is counted as "rejected" and thrown away unread
  * at most RATE_PER_SECOND messages per device per second (a device in a log storm cannot fill the database)
  * messages are parsed in memory (parsers.py) and written in batches every FLUSH_SECONDS
  * only user actions are stored; other messages (link up/down, routing ...) are only counted per device
"""
import ipaddress
import logging
import re
import socket
import time

from django.db import Error as DatabaseError
from django.db import connections
from django.utils import timezone

from application.commandlog import parsers
from application.commandlog import selectors
from application.commandlog import services

logger = logging.getLogger("dbms")
MAX_DATAGRAM = 8192
FLUSH_SECONDS = 2
FLUSH_EVENTS = 500
REFRESH_SECONDS = 60
RATE_PER_SECOND = 200
MAX_PENDING = 20000                      # kept in memory while the database is down, then the oldest go
SAME_MOMENT = 5                          # seconds: a second login / logout message for the same user is a repeat


class Receiver:
    def __init__(self, host="0.0.0.0", port=514, out=None):
        self.host, self.port, self.out = host, port, out or (lambda msg: None)
        self.exact, self.networks, self.net_cache = {}, [], {}
        self.events, self.stats = [], {}
        self.rejected, self.rejected_ip, self.dropped = 0, "", 0
        self.rate_second, self.rate = 0, {}
        self.recent = {}                     # (device, user, login|logout) -> (monotonic time, event)
        self.sock = None

    # ---- setup -------------------------------------------------------------------------------------------
    def bind(self):
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except OSError:
            pass
        sock.bind((self.host, self.port))
        sock.settimeout(1.0)
        self.sock = sock

    def refresh(self):
        """Re-read the allowed devices (NAS Clients); keeps the old list on a database error."""
        try:
            self.exact, self.networks = selectors.allowed_sources()
            self.net_cache = {}
        except DatabaseError:
            logger.warning("Syslog receiver: could not read the device list; keeping the previous one")
        finally:
            connections.close_all()
        return len(self.exact) + len(self.networks)

    def vendor_of(self, ip):
        """NAS vendor type of an allowed sender ("" when unknown), or None when the sender is not allowed."""
        if ip in self.exact:
            return self.exact[ip]
        if ip not in self.net_cache:
            found = None
            try:
                addr = ipaddress.ip_address(ip)
                best = -1
                for net, vendor in self.networks:
                    if addr.version == net.version and addr in net and net.prefixlen > best:
                        found, best = vendor, net.prefixlen
            except ValueError:
                pass
            if len(self.net_cache) > 50000:
                self.net_cache = {}
            self.net_cache[ip] = found
        return self.net_cache[ip]

    # ---- one message -----------------------------------------------------------------------------------------
    def handle(self, data, ip):
        if ip.startswith("::ffff:"):
            ip = ip[7:]
        vendor = self.vendor_of(ip)
        if vendor is None:
            self.rejected += 1
            self.rejected_ip = ip
            return
        second = int(time.monotonic())
        if second != self.rate_second:
            self.rate_second, self.rate = second, {}
        self.rate[ip] = self.rate.get(ip, 0) + 1
        if self.rate[ip] > RATE_PER_SECOND:
            self.dropped += 1
            return
        stat = self.stats.setdefault(ip, {"received": 0, "recognized": 0, "sample": ""})
        stat["received"] += 1
        if not stat.get("hostname"):
            stat["hostname"] = parsers.hostname(data[:MAX_DATAGRAM])
        event = parsers.parse(data[:MAX_DATAGRAM], vendor)
        if event:
            stat["recognized"] += 1
            if self.is_repeat(ip, event):
                return
            event["device_ip"], event["at"] = ip, timezone.now()
            self.events.append(event)
        else:
            text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
            stat["sample"] = re.sub(r"[\x00-\x1f\x7f]", " ", text).strip()[:500]

    def is_repeat(self, ip, event):
        """Huawei (and others) report one login or logout in two messages (SHELL and SSH): keep one, with the
        user's address and the protocol taken from whichever message has them."""
        if event["kind"] not in ("login", "logout"):
            return False
        key, now = (ip, event["username"], event["kind"]), time.monotonic()
        seen = self.recent.get(key)
        if len(self.recent) > 10000:
            self.recent = {k: v for k, v in self.recent.items() if now - v[0] <= SAME_MOMENT}
        if seen and now - seen[0] <= SAME_MOMENT:
            first = seen[1]
            first["source_ip"] = first["source_ip"] or event["source_ip"]
            first["command"] = first["command"] or event["command"]
            return True
        self.recent[key] = (now, event)
        return False

    # ---- writing -----------------------------------------------------------------------------------------------
    def flush(self, beat=False):
        if not (self.events or self.stats or beat):
            return True
        try:
            services.record(self.events, self.stats)
            if beat or self.rejected or self.dropped:
                services.heartbeat(self.port, self.rejected, self.rejected_ip, self.dropped)
                self.rejected, self.rejected_ip, self.dropped = 0, "", 0
            self.events, self.stats = [], {}
            return True
        except DatabaseError:
            logger.warning("Syslog receiver: database not reachable; %s events wait in memory", len(self.events),
                           exc_info=True)
            if len(self.events) > MAX_PENDING:
                self.events = self.events[-MAX_PENDING:]
            return False
        finally:
            connections.close_all()

    # ---- main loop ---------------------------------------------------------------------------------------------
    def run(self, should_stop=lambda: False):
        if self.sock is None:
            self.bind()
        n = self.refresh()
        try:
            services.heartbeat(self.port, started=True)
        except DatabaseError:
            logger.warning("Syslog receiver: database not reachable at start", exc_info=True)
        finally:
            connections.close_all()
        self.out(f"VAULT syslog receiver on udp://{self.host}:{self.port} - {n} device address(es) allowed")
        last_flush = last_refresh = last_beat = time.monotonic()
        while not should_stop():
            try:
                data, addr = self.sock.recvfrom(MAX_DATAGRAM)
                self.handle(data, addr[0])
            except socket.timeout:
                pass
            except OSError:
                logger.warning("Syslog receiver: socket error", exc_info=True)
                time.sleep(1)
            now = time.monotonic()
            beat = now - last_beat >= selectors.HEARTBEAT_SECONDS
            if beat or len(self.events) >= FLUSH_EVENTS or now - last_flush >= FLUSH_SECONDS:
                if self.flush(beat) and beat:
                    last_beat = now
                last_flush = now
            if now - last_refresh >= REFRESH_SECONDS:
                self.refresh()
                last_refresh = now
        self.flush(beat=True)
        self.sock.close()
