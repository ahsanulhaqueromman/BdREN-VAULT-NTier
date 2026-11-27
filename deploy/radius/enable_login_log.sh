#!/usr/bin/env bash
# Record WHICH DEVICE every RADIUS login came from, so the Authentication Audit page can show
# "user X logged in on device Y".
#
# FreeRADIUS's standard radpostauth table stores only username, result and time. This script:
#   1. adds four columns to radpostauth: nasipaddress (device IP), nasidentifier (device name it sends),
#      calledstationid (Called-Station-Id: port / AP / SSID the device reports) and callingstationid
#      (Calling-Station-Id: the address the person logged in FROM, e.g. the SSH client's IP)
#   2. changes ONLY the "post-auth" query of FreeRADIUS's SQL module so it fills those columns
#      (device IP = NAS-IP-Address, or the packet's source address when the device does not send it)
#      and never writes the typed password into radpostauth.pass; passwords written by older queries
#      are removed
#   3. checks the FreeRADIUS configuration; if the check fails the original file is put back
#   4. restarts FreeRADIUS
#
# Safe to run more than once (it does nothing when already done). Logins recorded BEFORE this script
# ran have no device; every login after it does.
#
# Usage:   sudo bash /opt/vault/deploy/radius/enable_login_log.sh
#          (reads RADIUS_DB_* from /opt/vault/.env; set ENV_FILE=/path/.env to use another file)
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/vault/.env}"
say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m OK\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run it with sudo:  sudo bash $0"
[ -r "$ENV_FILE" ] || die "Cannot read $ENV_FILE (set ENV_FILE=/path/to/.env)"
command -v mysql >/dev/null || die "The mysql client is not installed (apt install mariadb-client or mysql-client)"
command -v perl  >/dev/null || die "perl is required"

env_get() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]+|[[:space:]]+$//g' -e 's/^["'\'']//' -e 's/["'\'']$//' || true; }
DB_NAME="$(env_get RADIUS_DB_NAME)"; DB_NAME="${DB_NAME:-radius}"
DB_USER="$(env_get RADIUS_DB_USER)"; DB_USER="${DB_USER:-radius}"
DB_PASS="$(env_get RADIUS_DB_PASSWORD)"
DB_HOST="$(env_get RADIUS_DB_HOST)"; DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="$(env_get RADIUS_DB_PORT)"; DB_PORT="${DB_PORT:-3306}"
[ -n "$DB_PASS" ] || die "RADIUS_DB_PASSWORD is empty in $ENV_FILE"

# password in a private temp file, never on the command line
MYCNF="$(mktemp)"; chmod 600 "$MYCNF"; trap 'rm -f "$MYCNF"' EXIT
printf '[client]\nuser=%s\npassword=%s\nhost=%s\nport=%s\n' "$DB_USER" "$DB_PASS" "$DB_HOST" "$DB_PORT" > "$MYCNF"
sql() { mysql --defaults-extra-file="$MYCNF" -N -B "$DB_NAME" -e "$1"; }

# ---- 1. database columns ----------------------------------------------------------------------
say "Checking the radpostauth table in database '$DB_NAME'"
sql "SELECT 1 FROM radpostauth LIMIT 1" >/dev/null || die "Cannot read radpostauth (wrong database or permissions?)"
has_col() { [ "$(sql "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='radpostauth' AND column_name='$1'")" = "1" ]; }
if has_col nasipaddress; then ok "column nasipaddress already exists"
else sql "ALTER TABLE radpostauth ADD COLUMN nasipaddress VARCHAR(45) NOT NULL DEFAULT ''"; ok "added column nasipaddress"; fi
if has_col nasidentifier; then ok "column nasidentifier already exists"
else sql "ALTER TABLE radpostauth ADD COLUMN nasidentifier VARCHAR(64) NOT NULL DEFAULT ''"; ok "added column nasidentifier"; fi
if has_col calledstationid; then ok "column calledstationid already exists"
else sql "ALTER TABLE radpostauth ADD COLUMN calledstationid VARCHAR(50) NOT NULL DEFAULT ''"; ok "added column calledstationid"; fi
if has_col callingstationid; then ok "column callingstationid already exists"
else sql "ALTER TABLE radpostauth ADD COLUMN callingstationid VARCHAR(50) NOT NULL DEFAULT ''"; ok "added column callingstationid"; fi
if [ "$(sql "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='radpostauth' AND index_name='dbms_nasip'")" = "0" ]; then
  sql "CREATE INDEX dbms_nasip ON radpostauth (nasipaddress)"; ok "added an index for searching by device"
fi

# ---- 2. FreeRADIUS post-auth query --------------------------------------------------------------
QUERIES=""
for f in /etc/freeradius/3.0/mods-config/sql/main/mysql/queries.conf \
         /etc/freeradius/mods-config/sql/main/mysql/queries.conf \
         /etc/raddb/mods-config/sql/main/mysql/queries.conf; do
  [ -f "$f" ] && { QUERIES="$f"; break; }
done
[ -n "$QUERIES" ] || die "FreeRADIUS mysql queries.conf not found"
say "FreeRADIUS query file: $QUERIES"

# The TOP-LEVEL post-auth { ... } block (some packages also have post-auth blocks nested inside
# accounting { }, which must not be touched): found by postauth_query.pl next to this script.
PA="$(cd "$(dirname "$0")" && pwd)/postauth_query.pl"
[ -r "$PA" ] || die "$PA is missing (copy the whole deploy/radius folder)"
postauth_has() { perl "$PA" has "$1" "$QUERIES"; }
show_postauth() { perl "$PA" show "$1" | head -n 40 | sed 's/^/         | /' >&2; }
# A marker an older version of this script could leave behind made every later run fail: remove it.
if grep -q "DBMS_PATCH_INCOMPLETE" "$QUERIES"; then
  cp -p "$QUERIES" "$QUERIES.dbms-before-cleanup-$(date +%Y%m%d-%H%M%S)"
  sed -i '/DBMS_PATCH_INCOMPLETE/d' "$QUERIES"; ok "removed a leftover marker from an earlier failed run"
fi
# the query must not write the typed password (User-Password / Chap-Password) into radpostauth.pass
no_password() { ! postauth_has User-Password && ! postauth_has Chap-Password; }
if postauth_has nasipaddress && postauth_has nasidentifier && postauth_has calledstationid && postauth_has callingstationid && no_password; then
  ok "post-auth query already records the device and never the password"
  CHANGED=0
else
  BACKUP="$QUERIES.dbms-backup-$(date +%Y%m%d-%H%M%S)"
  cp -p "$QUERIES" "$BACKUP"; ok "backup saved: $BACKUP"
  # Replace the first query = "..." of the top-level post-auth block with one that also writes the
  # device columns. Rewriting it is more reliable than inserting into the packaged text, whose layout
  # differs between FreeRADIUS versions, and it also upgrades a query patched by an older version of
  # this script. Kept from the original query: the authdate format ('%S' on 3.0, '%S.%M' on 3.2) and the
  # optional ${..class...} column. Exit code 3 = no post-auth query found (the file is left as it was).
  set +e
  perl "$PA" patch "$QUERIES"
  rc=$?
  set -e
  if [ "$rc" != "0" ] || ! postauth_has nasipaddress || ! postauth_has nasidentifier || ! postauth_has calledstationid || ! postauth_has callingstationid || ! no_password; then
    cp -p "$BACKUP" "$QUERIES"
    printf '\033[1;31mERROR:\033[0m %s\n' "The post-auth query in $QUERIES has a layout this script does not know; nothing was changed." >&2
    echo "       This is the post-auth block found in the file (send it to the VAULT maintainer):" >&2
    show_postauth "$BACKUP"
    echo "       Or edit it by hand: add 'nasipaddress, nasidentifier, calledstationid, callingstationid' after 'authdate' in the" >&2
    echo "       column list, and , '%{%{NAS-IP-Address}:-%{Packet-Src-IP-Address}}', '%{NAS-Identifier}', '%{Called-Station-Id}', '%{Calling-Station-Id}'" >&2
    echo "       right after the authdate value ('%S' or '%S.%M'), then run this script again." >&2
    exit 1
  fi
  ok "post-auth query now records the device IP, identifier, Called-Station-Id and Calling-Station-Id, and no password"
  CHANGED=1
fi

# ---- 2b. remove the passwords older queries wrote into radpostauth.pass --------------------------
WIPED="$(sql "UPDATE radpostauth SET pass='' WHERE pass<>''; SELECT ROW_COUNT()")" || die "Cannot clear radpostauth.pass"
if [ "${WIPED:-0}" != "0" ]; then ok "removed $WIPED clear-text password(s) from earlier login records"
else ok "no password is stored in the login records"; fi

# ---- 3. check the configuration, then restart ---------------------------------------------------
RADIUSD="$(command -v freeradius || command -v radiusd || true)"
[ -n "$RADIUSD" ] || die "freeradius binary not found"
say "Checking the FreeRADIUS configuration"
CHECK_LOG=/tmp/dbms-radius-check.log
check_errors() {   # the lines of the check that say what is wrong (FreeRADIUS prints a lot before them)
  { grep -iE "error|fail|expect|invalid|unknown|no such|parse" "$CHECK_LOG" || tail -n 15 "$CHECK_LOG"; } \
    | tail -n 15 | sed 's/^/         | /' >&2
}
if ! "$RADIUSD" -C >"$CHECK_LOG" 2>&1; then
  if [ "${CHANGED}" != "1" ]; then
    printf '\033[1;31mERROR:\033[0m %s\n' "The FreeRADIUS configuration is invalid (this script changed nothing). FreeRADIUS says:" >&2
    check_errors
    echo "       Fix that first (full output: sudo freeradius -XC), then run this script again." >&2
    exit 1
  fi
  FAILED="$QUERIES.dbms-failed-$(date +%Y%m%d-%H%M%S)"
  cp -p "$QUERIES" "$FAILED"
  cp -p "$BACKUP" "$QUERIES"
  if "$RADIUSD" -C >/dev/null 2>&1; then WHO="the changed post-auth query"; else WHO="something else in the configuration (it fails without this change too)"; fi
  printf '\033[1;31mERROR:\033[0m %s\n' "FreeRADIUS rejected the configuration; the cause is $WHO. The original file was restored. FreeRADIUS says:" >&2
  check_errors
  echo "       The rejected version is kept as $FAILED; full output: $CHECK_LOG" >&2
  echo "       This is the post-auth block that was tried (send this and the lines above to the VAULT maintainer):" >&2
  show_postauth "$FAILED"
  exit 1
fi
ok "configuration is valid"
if [ "${CHANGED}" = "1" ]; then
  say "Restarting FreeRADIUS"
  systemctl restart freeradius 2>/dev/null || systemctl restart radiusd
  ok "FreeRADIUS restarted"
fi
echo
ok "Done. New logins are recorded with their device. Open RADIUS / AAA -> Authentication Audit."
