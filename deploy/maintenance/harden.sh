#!/usr/bin/env bash
# Server hardening for VAULT. Run by install.sh; safe to run again any time:
#     sudo bash /opt/vault/deploy/maintenance/harden.sh
#
#   1. nginx rate limit on /login and /setup: 10 requests a minute per address (burst 5), then 429.
#   2. fail2ban: an address that fails SSH logins 5 times, or keeps hitting the login rate limit,
#      is banned for 1 day.
#   3. unattended-upgrades: Debian/Ubuntu security updates install automatically every day.
#
# Each part checks itself (nginx -t, fail2ban-client -t) and puts the previous files back on failure.
set -uo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
c_b='\033[1;34m'; c_g='\033[1;32m'; c_y='\033[1;33m'; c_r='\033[1;31m'; c_0='\033[0m'
say()  { printf "${c_b}==>${c_0} %s\n" "$*"; }
ok()   { printf "${c_g}  ✓${c_0} %s\n" "$*"; }
warn() { printf "${c_y}  !${c_0} %s\n" "$*"; WARNED=1; }
die()  { printf "${c_r}ERROR:${c_0} %s\n" "$*" >&2; exit 1; }
WARNED=0

[ "$(id -u)" -eq 0 ] || die "Run it with sudo:  sudo bash $0"
apt_install() {
  local need=(); for p in "$@"; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
  [ ${#need[@]} -eq 0 ] && return 0
  { apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}"; } >/dev/null 2>&1
}

# ---- 1. nginx: login rate limit ---------------------------------------------------------------------------
if command -v nginx >/dev/null 2>&1; then
  say "nginx"
  SITE="$(grep -RlE "proxy_pass[[:space:]]+https?://(127\.0\.0\.1|localhost):[0-9]+" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null | head -n1 || true)"
  if [ -z "$SITE" ]; then
    warn "no nginx site proxies to VAULT; nginx part skipped"
  else
    SITE="$(readlink -f "$SITE")"
    PORT="$(grep -oE "proxy_pass[[:space:]]+https?://(127\.0\.0\.1|localhost):[0-9]+" "$SITE" | head -n1 | grep -oE '[0-9]+$')"
    LIMIT=/etc/nginx/conf.d/vault-ratelimit.conf
    for f in "$SITE" "$LIMIT"; do [ -f "$f" ] && cp -p "$f" "$f.vault-bak-$STAMP"; done
    nginx_restore() {
      for f in "$SITE" "$LIMIT"; do
        if [ -f "$f.vault-bak-$STAMP" ]; then mv -f "$f.vault-bak-$STAMP" "$f"; else rm -f "$f"; fi
      done
    }
    cat > "$LIMIT" <<'EOF'
# Written by deploy/maintenance/harden.sh: VAULT /login and /setup, 10 requests a minute per address (burst 5).
limit_req_zone $binary_remote_addr zone=vault_login:10m rate=10r/m;
limit_req_status 429;
limit_req_log_level warn;
EOF
    # rate-limited login pages, placed before the first "location / {"
    if ! grep -q "zone=vault_login" "$SITE"; then
      awk -v port="$PORT" 'BEGIN{done=0}
        !done && /^[ \t]*location[ \t]+\/[ \t]*\{/ {
          print "    # vault-hardening: slow down password guessing on the sign-in pages"
          print "    location ~ ^/(login|setup)$ {"
          print "        limit_req zone=vault_login burst=5 nodelay;"
          print "        proxy_pass http://127.0.0.1:" port ";"
          print "        proxy_set_header Host $host;"
          print "        proxy_set_header X-Forwarded-For $remote_addr;"
          print "        proxy_set_header X-Forwarded-Proto $scheme;"
          print "        proxy_set_header X-Forwarded-Host $host;"
          print "        proxy_read_timeout 120s;"
          print "    }"
          print ""
          done=1 }
        {print}' "$SITE" > "$SITE.new" && cat "$SITE.new" > "$SITE"; rm -f "$SITE.new"
    fi
    if nginx -t >/dev/null 2>&1; then
      systemctl reload nginx
      rm -f "$SITE.vault-bak-$STAMP" "$LIMIT.vault-bak-$STAMP"
      grep -q "zone=vault_login" "$SITE" && ok "sign-in pages limited to 10 requests a minute per address" \
        || warn "no 'location / {' in $SITE: login rate limit not added"
    else
      nginx -t 2>&1 | tail -n 3 | sed 's/^/      /'
      nginx_restore; warn "nginx rejected the change; previous files restored"
    fi
  fi
fi

# ---- 2. fail2ban ------------------------------------------------------------------------------------------
say "fail2ban"
if apt_install fail2ban; then
  JAIL=/etc/fail2ban/jail.d/vault.local
  [ -f "$JAIL" ] && cp -p "$JAIL" "$JAIL.vault-bak-$STAMP"
  if [ -f /var/log/auth.log ]; then SSH_BACKEND=auto; else SSH_BACKEND=systemd; fi
  {
    echo "# Written by deploy/maintenance/harden.sh"
    echo "[DEFAULT]"
    echo "ignoreip = 127.0.0.1/8 ::1"
    echo "bantime  = 1d"
    echo "findtime = 10m"
    echo
    echo "[sshd]"
    echo "enabled  = true"
    echo "backend  = $SSH_BACKEND"
    echo "maxretry = 5"
    if command -v nginx >/dev/null 2>&1 && [ -f /etc/fail2ban/filter.d/nginx-limit-req.conf ]; then
      echo
      echo "# an address that keeps hitting the /login rate limit"
      echo "[nginx-limit-req]"
      echo "enabled  = true"
      echo "port     = http,https"
      echo "logpath  = /var/log/nginx/error.log"
      echo "maxretry = 10"
    fi
  } > "$JAIL"
  if fail2ban-client -t >/dev/null 2>&1; then
    systemctl enable fail2ban >/dev/null 2>&1; systemctl restart fail2ban
    rm -f "$JAIL.vault-bak-$STAMP"
    ok "fail2ban: 5 failed SSH logins (or repeated login flooding) = banned for 1 day"
  else
    fail2ban-client -t 2>&1 | tail -n 3 | sed 's/^/      /'
    if [ -f "$JAIL.vault-bak-$STAMP" ]; then mv -f "$JAIL.vault-bak-$STAMP" "$JAIL"; else rm -f "$JAIL"; fi
    warn "fail2ban rejected the configuration; previous one restored"
  fi
else
  warn "could not install fail2ban (apt); try: sudo apt install fail2ban"
fi

# ---- 3. automatic security updates ------------------------------------------------------------------------
say "Automatic security updates"
if apt_install unattended-upgrades; then
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
// Written by deploy/maintenance/harden.sh: refresh package lists and install security updates every day.
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
  systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
  ok "security updates install automatically every day"
else
  warn "could not install unattended-upgrades (apt); try: sudo apt install unattended-upgrades"
fi

echo
if [ "$WARNED" = 1 ]; then warn "Hardening finished with warnings (see above)."; exit 2; fi
ok "Hardening done."
