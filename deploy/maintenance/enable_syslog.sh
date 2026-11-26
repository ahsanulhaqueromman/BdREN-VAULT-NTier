#!/usr/bin/env bash
# Session Log: install and start the syslog receiver (service vault-syslog) that keeps who ran which
# command on the network devices, and open its port in the firewall only for the devices on NAS Clients.
#
# Usage:  sudo bash /opt/vault/deploy/maintenance/enable_syslog.sh        (safe to run again; install.sh runs it too)
#
# Port: UDP 514, or SYSLOG_PORT in .env. The receiver runs as the app's own user; systemd gives it only the
# right to use a port below 1024 (CAP_NET_BIND_SERVICE), nothing else. It accepts messages only from
# addresses on NAS Clients and throws everything else away.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vault}"; ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
UNIT=/etc/systemd/system/vault-syslog.service
SRC_UNIT="$APP_DIR/deploy/systemd/vault-syslog.service"
ok()   { printf '\033[1;32m OK\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run it with sudo:  sudo bash $0"
[ -f "$SRC_UNIT" ] || die "$SRC_UNIT not found (install the new package first)"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found"
[ -x "$APP_DIR/.venv/bin/python" ] || die "$APP_DIR/.venv not found (run install.sh first)"
SVC_USER="${SVC_USER:-$(stat -c %U "$ENV_FILE")}"
id "$SVC_USER" >/dev/null 2>&1 || die "user $SVC_USER not found"
envv() { { grep -E "^$1=" "$ENV_FILE" || true; } | tail -n1 | cut -d= -f2- | tr -d '\r' | sed -E "s/^[\"'](.*)[\"']$/\1/"; }
PORT="$(envv SYSLOG_PORT)"; PORT="${PORT:-514}"
[[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die "SYSLOG_PORT in $ENV_FILE is not a port number"

# 1. the port must be free (or already ours): another syslog server (rsyslog with imudp, syslog-ng) cannot share it
holder="$(ss -H -ulnp "sport = :$PORT" 2>/dev/null || true)"
if [ -n "$holder" ] && ! systemctl is-active --quiet vault-syslog; then
  who="$(printf '%s\n' "$holder" | grep -oE 'users:\(\("[^"]+"' | head -n1 | sed -E 's/users:\(\("//')"
  die "UDP $PORT is already used by ${who:-another program}. Either stop its network listener (rsyslog: comment out the imudp lines in /etc/rsyslog.conf, then: sudo systemctl restart rsyslog) or set another port, for example SYSLOG_PORT=5514 in $ENV_FILE, and send the device logs to that port. Then run this script again."
fi

# 2. the service, filled in for this server
tmp="$(mktemp)"
sed -e "s|^User=.*|User=$SVC_USER|" -e "s|^Group=.*|Group=$SVC_USER|" -e "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|" \
    -e "s|^ExecStart=.*|ExecStart=$APP_DIR/.venv/bin/python manage.py syslog_receive --port $PORT|" "$SRC_UNIT" > "$tmp"
install -m 644 -o root -g root "$tmp" "$UNIT"; rm -f "$tmp"
systemctl daemon-reload
systemctl enable vault-syslog >/dev/null 2>&1
systemctl restart vault-syslog
for _ in 1 2 3 4 5 6; do systemctl is-active --quiet vault-syslog && break; sleep 1; done
sleep 2
if systemctl is-active --quiet vault-syslog; then
  ok "syslog receiver running on UDP $PORT (service vault-syslog)"
else
  journalctl -u vault-syslog -n 15 --no-pager >&2 || true
  die "the syslog receiver did not start (above: its last log lines). Check: sudo journalctl -u vault-syslog -n 50"
fi

# 3. firewall: UDP $PORT open only for NAS Clients (the same rule set that keeps RADIUS closed to everyone else)
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  if [ -f "$APP_DIR/deploy/radius/enable_firewall_sync.sh" ] && \
     APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" SVC_USER="$SVC_USER" bash "$APP_DIR/deploy/radius/enable_firewall_sync.sh" >/dev/null 2>&1; then
    ok "firewall: UDP $PORT open only for the devices on NAS Clients (follows NAS changes automatically)"
  else
    warn "could not set the firewall rules automatically. Allow each device by hand:"
    warn "  sudo ufw allow proto udp from <device-ip> to any port $PORT comment vault-syslog"
  fi
else
  ok "ufw is not active: nothing to open (the receiver itself still ignores addresses that are not on NAS Clients)"
fi
printf '\nDone. Turn on command logging on each device: VAULT > RADIUS / AAA > Device Setup, step "Command logging".\n'
printf 'What arrives is shown on RADIUS / AAA > Session Log.\n'
