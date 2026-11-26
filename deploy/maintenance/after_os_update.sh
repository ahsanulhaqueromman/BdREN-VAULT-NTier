#!/usr/bin/env bash
# After an Ubuntu / Debian update (or a release upgrade): check that VAULT still works.
#
# READ-ONLY: this script changes nothing. It checks
#   1. the Python environment still loads Django with the server's current Python
#   2. the services run: vault, vault-syslog, freeradius, nginx, mariadb
#   3. the FreeRADIUS configuration is valid and still has VAULT's SQL module and device-limit policy
#   4. the portal answers its health check
# and prints the one command that fixes whatever is wrong.
#
# Usage:  sudo bash /opt/vault/deploy/maintenance/after_os_update.sh
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/vault}"
FR="${FR_DIR:-/etc/freeradius/3.0}"
bad=0
ok()   { printf '\033[1;32m OK\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mBAD\033[0m %s\n' "$*"; bad=1; }
FIX="cd <your VAULT git folder> && git pull && sudo bash deploy/install.sh     (safe to run again; it repairs the items above)"

[ "$(id -u)" -eq 0 ] || { echo "Run it with sudo:  sudo bash $0" >&2; exit 1; }

# 1. Python environment
sys_py="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo '?')"
if "$APP_DIR/.venv/bin/python" -c "import sys, django; assert '%d.%d' % sys.version_info[:2] == '$sys_py'" >/dev/null 2>&1; then
  ok "Python environment matches the server's Python $sys_py"
else
  fail "Python environment is broken or built for another Python (server has $sys_py): the installer rebuilds it"
fi

# 2. services
for svc in mariadb nginx freeradius vault vault-syslog; do
  if systemctl is-active --quiet "$svc"; then ok "service $svc is running"
  elif systemctl list-unit-files 2>/dev/null | grep -q "^$svc\.service"; then fail "service $svc is not running  (try: sudo systemctl restart $svc)"
  else printf '  -  service %s is not installed on this server\n' "$svc"; fi
done

# 3. FreeRADIUS
if command -v freeradius >/dev/null 2>&1; then
  if freeradius -XC >/dev/null 2>&1; then ok "FreeRADIUS configuration is valid"
  else fail "FreeRADIUS configuration check failed  (see: sudo freeradius -XC)"; fi
  [ -e "$FR/mods-enabled/sql" ] && ok "FreeRADIUS SQL module is enabled" || fail "FreeRADIUS SQL module is not enabled (an update may have restored the package's files)"
  if [ -f "$FR/policy.d/dbms_device_limit" ] && grep -q "dbms_device_limit" "$FR/sites-enabled/default" 2>/dev/null; then
    ok "VAULT's device-limit policy is installed"
  else
    fail "VAULT's FreeRADIUS policy is missing from $FR (an update may have replaced the file)"
  fi
fi

# 4. portal
if curl -ks --max-time 8 https://127.0.0.1/healthz 2>/dev/null | grep -q '"ok"'; then ok "portal health check answers"
else fail "portal health check does not answer on https://127.0.0.1/healthz"; fi

echo
if [ "$bad" -eq 0 ]; then
  echo "Everything VAULT needs is in place. Log in to one device with a RADIUS user to finish."
else
  echo "Some checks failed. The usual fix:"
  echo "  $FIX"
  echo "Then run this script again."
  exit 1
fi
