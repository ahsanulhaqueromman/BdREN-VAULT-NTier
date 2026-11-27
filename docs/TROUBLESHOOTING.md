# Troubleshooting

Basic commands to find and fix common problems on a VAULT server. Run them on the server over SSH.
Paths assume the default install: the app in `/opt/vault`, the service `vault`, FreeRADIUS config in
`/etc/freeradius/3.0`.

**Start here:** most problems show up in one of these three commands.

```bash
systemctl status vault freeradius nginx mariadb --no-pager     # is everything running?
sudo journalctl -u vault -n 100 --no-pager                      # VAULT application log
curl -k https://127.0.0.1/healthz                               # {"status": "ok"} = app and database fine
```

---

## Contents

1. [Website does not open](#1-website-does-not-open)
2. [Cannot sign in to the portal](#2-cannot-sign-in-to-the-portal)
3. [Locked out of the server over SSH (fail2ban)](#3-locked-out-of-the-server-over-ssh-fail2ban)
4. [Backups fail](#4-backups-fail)
5. [Device login with a RADIUS user fails](#5-device-login-with-a-radius-user-fails)
6. [Authentication Audit shows no device (login logging)](#6-authentication-audit-shows-no-device-login-logging)
7. [Session Log shows nothing (syslog)](#7-command-history-shows-nothing-syslog)
8. [Database problems](#8-database-problems)
9. [Disk full](#9-disk-full)
10. [After an update](#10-after-an-update)
11. [Useful file locations](#11-useful-file-locations)

---

## 1. Website does not open

```bash
systemctl status vault nginx --no-pager
sudo journalctl -u vault -n 100 --no-pager
sudo nginx -t                                   # nginx configuration valid?
sudo tail -n 50 /var/log/nginx/error.log
curl -s http://127.0.0.1:8495/healthz           # the app itself, without nginx
sudo ufw status                                 # 443/tcp must be allowed
```

| Symptom | Fix |
|---|---|
| `vault` is not running | `sudo systemctl restart vault`, then read the log above for the error |
| `502 Bad Gateway` | nginx is up but the app is not: restart `vault` and check its log |
| `Bad Request (400)` | The address you opened is not in `DJANGO_ALLOWED_HOSTS` in `/opt/vault/.env`. Add it, then `sudo systemctl restart vault` |
| Page loads without styling or old design | Press **Ctrl+F5** once in the browser |
| Connection times out | Firewall: `sudo ufw allow 443/tcp` |

---

## 2. Cannot sign in to the portal

- **"Too many attempts"**: 5 wrong passwords lock that address and username for 5 minutes. Wait, or
  restart the app to clear it: `sudo systemctl restart vault`.
- **Forgot the administrator password:**

  ```bash
  cd /opt/vault
  sudo -u vault .venv/bin/python manage.py changepassword <username>
  ```

- **Signed out often**: the idle timeout is `DBMS_SESSION_MINUTES` in `/opt/vault/.env` (default 15).

---

## 3. Locked out of the server over SSH (fail2ban)

fail2ban bans an address after 5 failed SSH logins, for 1 day. From another address or the server
console:

```bash
sudo fail2ban-client status sshd                   # list banned addresses
sudo fail2ban-client set sshd unbanip <your-IP>    # remove the ban
```

The portal login has its own jail; `sudo fail2ban-client status` lists every jail.

---

## 4. Backups fail

Open **Backup Jobs** or **Activity Logs** in the portal for the device's error message, then test from the
server:

```bash
ping -c 3 <device-ip>                     # reachable?
nc -zv <device-ip> 22                     # SSH port open?
ssh <backup-user>@<device-ip>             # can the backup account log in?
sudo journalctl -u vault -n 200 --no-pager | grep -i <device-ip>
```

| Error / symptom | Usual cause and fix |
|---|---|
| Timeout / unreachable | Device offline, wrong IP, or a firewall between the server and the device |
| Authentication failed | Wrong username or password saved for the device; edit the device and save it again |
| `SSH host key CHANGED` | Possible man-in-the-middle, or the device was replaced / re-keyed. Only if that is expected, remove its saved key: `sudo grep -l "<device-ip>" /opt/vault/data/hostkeys/*` and delete the file it lists; the next backup saves the new key |
| Backup succeeds but the file is short | The backup account may see only part of the configuration. Give it permission to view the full configuration (see [DEPLOY.md](DEPLOY.md#backup-account-on-the-devices)) |
| Whole run is slow | Raise **Parallel SSH sessions** in System Settings (and `DBMS_MAX_WORKERS` in `.env`, max 200) |

---

## 5. Device login with a RADIUS user fails

```bash
sudo bash /opt/vault/deploy/radius/check_levels.sh   # read-only check of the whole chain
sudo freeradius -XC                                   # configuration valid?
sudo ss -lunp | grep 1812                             # FreeRADIUS listening on UDP 1812?
sudo ufw status | grep 1812                           # device IP allowed?
```

See exactly what FreeRADIUS does with one login (stops the service briefly):

```bash
sudo systemctl stop freeradius
sudo freeradius -X            # log in on the device now and read the output; Ctrl+C to stop
sudo systemctl start freeradius
```

| Symptom | Fix |
|---|---|
| Nothing appears in `freeradius -X` | The packet never arrives: device not in **NAS Clients**, wrong RADIUS server IP on the device, or a firewall in between |
| `Ignoring request from unknown client` | Add the device under **NAS Clients** (the source IP must match) |
| `Shared secret is incorrect` | The secret on the device differs from the one in **NAS Clients** |
| `Access-Reject` for a valid user | Wrong password, the user is not allowed on that device, or the source address is blocked after an unknown-username login (see **Authentication Audit**) |
| Logged in with the wrong level | Run `check_levels.sh`; it names the cause and the fix |
| `Access-Reject` and `freeradius -X` says `No NT-Password` (MikroTik, MS-CHAPv2) | The password was saved before VAULT kept the NT hash (marked "No MikroTik login" on RADIUS Users). Set the user's password again |
| `Access-Reject` and `freeradius -X` mentions CHAP-Password | CHAP needs the clear text, which VAULT never stores. Set the device to PAP or MS-CHAPv2 |
| A device was fine, then every request is dropped with a Message-Authenticator message | BlastRADIUS protection (`require_message_authenticator = auto`): the device sent Message-Authenticator once and now sends a request without it. Update its firmware or its RADIUS settings so it always sends it |

> Every device must keep one **local** administrator account, so you can still log in when RADIUS is down.

### Check RADIUS security (both servers)

Make sure you are on the server you mean (both prompts may say `root@bdren`):

```bash
hostname -I                                            # the server's address
```

Passwords stored as hashes, none in clear text:

```bash
sudo mysql radius -e "SELECT attribute, COUNT(*) FROM radcheck WHERE attribute IN ('Cleartext-Password','SSHA2-256-Password') GROUP BY attribute;"
```

Only `SSHA2-256-Password` should be listed. If `Cleartext-Password` is there too, run
`sudo bash /opt/vault/deploy/install.sh`, or convert them by hand (same passwords):

```bash
sudo -u vault /opt/vault/.venv/bin/python /opt/vault/manage.py radius_hash_passwords
```

BlastRADIUS (CVE-2024-3596) protection:

```bash
freeradius -v | head -1                                # 3.2.5 or newer (or a package with the fix)
grep -n "^\s*require_message_authenticator\|^\s*limit_proxy_state" /etc/freeradius/3.0/radiusd.conf
```

Both lines must say `= auto` (FreeRADIUS 3.2.5 already has them; the lines starting with `#` are only
comments). If they are missing: `sudo bash /opt/vault/deploy/radius/enable_blastradius.sh`. An older
FreeRADIUS has to be updated first: `sudo apt update && sudo apt install --only-upgrade freeradius`.

---

## 6. Authentication Audit shows no device (login logging)

The installer runs this automatically; run it again after fixing anything:

```bash
sudo bash /opt/vault/deploy/radius/enable_login_log.sh
```

If it still fails, it prints the reason and the post-auth block it found. To set it up by hand:

**a) Add the four columns** (skip any that already exist; "Duplicate column name" means it is there):

```bash
sudo mysql radius
```
```sql
ALTER TABLE radpostauth ADD COLUMN nasipaddress    VARCHAR(45) NOT NULL DEFAULT '';
ALTER TABLE radpostauth ADD COLUMN nasidentifier   VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE radpostauth ADD COLUMN calledstationid  VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE radpostauth ADD COLUMN callingstationid VARCHAR(50) NOT NULL DEFAULT '';
EXIT;
```

(On a server where MariaDB root has a password, use `mysql -u root -p radius` instead of `sudo mysql radius`.)

**b) Change the post-auth query.** Back up the file first, then open it:

```bash
F=/etc/freeradius/3.0/mods-config/sql/main/mysql/queries.conf
sudo cp -p $F $F.manual-backup
grep -n "^post-auth" $F                  # line of the TOP-LEVEL post-auth { block
sudo nano +<line> $F
```

Edit the `query = "..."` directly inside the **top-level** `post-auth {` block (not the one inside
`accounting { }`). On FreeRADIUS **3.2** (authdate `'%S.%M'`, with `${..class...}`):

```
	query = "\
		INSERT INTO ${..postauth_table} \
			(username, pass, reply, authdate, nasipaddress, nasidentifier, calledstationid, callingstationid ${..class.column_name}) \
		VALUES ( \
			'%{SQL-User-Name}', \
			'', \
			'%{reply:Packet-Type}', \
			'%S.%M', \
			'%{Packet-Src-IP-Address}', \
			'%{NAS-Identifier}', \
			'%{Called-Station-Id}', \
			'%{Calling-Station-Id}' \
			${..class.reply_xlat})"
```

On FreeRADIUS **3.0** (authdate `'%S'`, no class column):

```
	query = "\
		INSERT INTO ${..postauth_table} \
			(username, pass, reply, authdate, nasipaddress, nasidentifier, calledstationid, callingstationid) \
		VALUES ( \
			'%{SQL-User-Name}', \
			'', \
			'%{reply:Packet-Type}', \
			'%S', \
			'%{Packet-Src-IP-Address}', \
			'%{NAS-Identifier}', \
			'%{Called-Station-Id}', \
			'%{Calling-Station-Id}')"
```

**c) Check and restart:**

```bash
sudo freeradius -XC && sudo systemctl restart freeradius
```

If the check fails, put the backup back: `sudo cp -p $F.manual-backup $F && sudo systemctl restart freeradius`.
Then log in to a device once and look at **Authentication Audit**.

---

### From is empty

**From** is the address the person logged in from. It comes from the device's RADIUS request
(Calling-Station-Id), and when the device sends none (Huawei switches, for one) from the device's syslog in
the Session Log: the same user's login line, else the closest command line, up to 10 minutes after the login.
Still empty: the device does not send its logins to VAULT (Device Setup, step "Command logging"; Huawei:
`info-center source SSH channel loghost log level informational`).

The address is the one the device sees. Behind NAT, a jump server or a VPN that is the NAT / jump server / VPN
address (for example the same address for everyone), not the person's own public address.

---

## 7. Session Log shows nothing (syslog)

Session Log is filled by the **vault-syslog** service, which receives the devices' syslog on UDP 514.
The page itself says what is wrong at the top (receiver not installed, not running, or messages ignored).
Press **What to do** on the warning for the steps; a warning about ignored or dropped messages can be
cleared with **Done, dismiss** once it is handled (it comes back only with the next such message).

**a) Is the receiver running?**

```bash
systemctl status vault-syslog --no-pager
sudo journalctl -u vault-syslog -n 50 --no-pager
sudo ss -ulnp | grep ':514 '                    # must show python (the receiver)
```

Not installed or not running: `sudo bash /opt/vault/deploy/maintenance/enable_syslog.sh`. If it says the port is used
by another program (usually rsyslog with network input), comment out the `imudp` lines in
`/etc/rsyslog.conf` and `sudo systemctl restart rsyslog`, or set `SYSLOG_PORT=5514` in `.env`, run the
script again and send the device logs to that port.

**b) Do the logs reach the server?**

```bash
sudo tcpdump -ni any udp port 514 -c 10        # run, then log in to the device and type a command
sudo ufw status | grep 514                      # with the firewall on, the device needs its own rule
```

| What you see | Cause and fix |
|---|---|
| Nothing in tcpdump | The device does not send: check its syslog settings (Device Setup, step "Command logging") and that it can reach the server (`ping` from the device) |
| Packets arrive, page says "messages were ignored" | They come from an address that is not on NAS Clients (often a loopback or management address). Make the device send from its NAS address (`info-center loghost source`, `logging source-interface`, `source-address`), or add that address on NAS Clients |
| Packets arrive, no ufw rule for the device | `sudo /usr/local/sbin/vault-radius-firewall` (adds UDP 514 for every NAS Clients address) |
| A device deleted from NAS Clients is still in "Devices sending logs" | Update VAULT: the list shows only devices on NAS Clients |
| Device listed under "Devices sending logs" but "No user actions yet" | The device sends other logs but not its commands. Open **Last message received** to see its format, then turn on command logging (Huawei: `info-center enable` and `info-center loghost <server>`; Cisco: `archive` / `log config` / `notify syslog`) |

**c) Cisco (IOS / IOS-XE)**

| What you see | Cause and fix |
|---|---|
| Configuration changes arrive, `show` / `ping` do not | Cisco logs configuration commands only. Add the event manager applet from Device Setup, step "Command logging" (needs EEM 3.0 or newer: IOS 15 / IOS-XE) |
| `show running-config \| include x` arrives as `show running-config` | Cisco removes the part after the pipe before the applet sees the command; only TACACS+ command accounting sends it |
| The session shows "No logout" | Cisco sends its logout message at level 6 (informational), below `logging trap notifications`. The session shows "No logout" 5 minutes after the last command, or at once with RADIUS accounting: `aaa accounting exec default start-stop group radius` |
| The device shows by address, not by name | Add `logging origin-id hostname`, or give the device a name on NAS Clients or in Device Inventory |
| The router sends from a different address per path | Each VAULT server sees the address the packets leave from (a VRF or management interface may differ). Check with `sudo tcpdump -ni any udp port 514` and put that address on NAS Clients, or set `logging source-interface` |

**d) Test the receiver from the server itself** (only works when 127.0.0.1 is on NAS Clients; remove it afterwards):

```bash
logger -n 127.0.0.1 -P 514 -d '%%01SHELL/5/CMDRECORD(s)[1]:Recorded command information. (Task=VT0, Ip=10.0.0.5, VpnName=, User=test, AuthenticationMethod="RADIUS", Command="display version")'
```

---

## 8. Database problems

```bash
systemctl status mariadb --no-pager
sudo journalctl -u mariadb -n 50 --no-pager
sudo mysql -e "SHOW DATABASES;"                       # dbms and radius must be listed
grep -E "^(DBMS_DB_|RADIUS_DB_)" /opt/vault/.env      # connection settings the app uses
```

| Symptom | Fix |
|---|---|
| App log says `Access denied for user` | The password in `.env` differs from MariaDB's; fix it in `.env` and restart `vault` |
| `Can't connect to MySQL server` | `sudo systemctl restart mariadb` |
| RADIUS pages say the database is not reachable | Check the `RADIUS_DB_*` settings in `.env` |

---

## 9. Disk full

Backups and logs stop when the disk is full.

```bash
df -h                                          # free space
sudo du -sh /opt/vault/data/backups            # saved configurations
sudo du -sh /var/backups/vault /var/backups/vault-dr
sudo journalctl --disk-usage
```

Free space: set a retention period in **System Settings → Data retention**, remove old update copies in
`/var/backups/vault/`, or shrink the system journal with `sudo journalctl --vacuum-size=500M`.

---

## 10. After an update

```bash
sudo journalctl -u vault -n 100 --no-pager       # errors after the restart?
cd /opt/vault && sudo -u vault .venv/bin/python manage.py showmigrations | grep "\[ \]"   # unapplied migrations
```

If the update failed, the installer restores the previous version from `/var/backups/vault/` on its own.
Press **Ctrl+F5** in the browser once after every update.

---

## 11. Useful file locations

| Path | Contents |
|---|---|
| `/opt/vault/` | The application |
| `/opt/vault/.env` | Settings and passwords |
| `/opt/vault/data/secret.key` | Key for saved device passwords: keep a copy off the server |
| `/opt/vault/data/backups/` | Saved device configurations |
| `/etc/systemd/system/vault.service` | Service definition (app on 127.0.0.1:8495) |
| `/etc/systemd/system/vault-syslog.service` | Syslog receiver for Session Log (UDP 514) |
| `/etc/nginx/sites-available/dbms` | nginx site |
| `/etc/freeradius/3.0/` | FreeRADIUS configuration |
| `/var/backups/vault/` | Previous versions saved by updates |
| `/var/backups/vault-dr/` | Disaster-recovery copies from `deploy/maintenance/backup_vault.sh` |
