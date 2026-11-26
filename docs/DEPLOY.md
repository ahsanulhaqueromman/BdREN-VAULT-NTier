# Deploy

The same installer sets up a new Ubuntu / Debian server and updates an existing one.

## New server

```bash
unzip -q BdREN-VAULT.zip -d /tmp/dbms-new
sudo bash /tmp/dbms-new/vault/deploy/install.sh
```

It asks for the address people will use, the first administrator, and whether to install FreeRADIUS and HTTPS
(both default to yes), then installs everything: Python packages, MariaDB and both databases, FreeRADIUS with
the DBMS policies, nginx on HTTPS, the `dbms` service and a final health check. Passwords it generates are
stored only in `/opt/vault/.env`.

## Update (3 commands)

```bash
rm -rf /tmp/dbms-new && unzip -q -o ~/BdREN-VAULT.zip -d /tmp/dbms-new
sudo SVC_USER="$(systemctl show -p User --value vault || echo vault)" bash /tmp/dbms-new/vault/deploy/install.sh
sudo bash /opt/vault/deploy/radius/check_levels.sh
```

The update keeps `.env`, `data/` (backups, `secret.key`) and the databases; replaces the program files exactly
(removes files that no longer exist), migrates the database, refreshes the RADIUS level attributes and restarts.
The previous version is saved in `/var/backups/vault/` and restored automatically if anything fails. Then open
the site and press **Ctrl+F5** once.

## Backup account on the devices

VAULT needs an account on each device that can **see the whole configuration but change nothing**. A plain
read-only level is often not enough: the device then returns only part of the configuration (or refuses the
command) while the backup still looks successful. Set this up once per device. Commands differ between OS
versions, so **test on one device first** and compare the saved file with a full `show running-config`.

| Vendor | One-time setup (example) |
|---|---|
| Cisco IOS / IOS-XE | `privilege exec level 3 show running-config` and `file privilege 3`, backup user at privilege 3. On some versions `privilege exec level 3 show running-config view full` is enough. |
| Huawei VRP | `command-privilege level 1 view shell display current-configuration` |
| Juniper Junos | `set system login class backup-ro permissions [ view view-configuration ]` (add `secret` to include secrets) |
| MikroTik RouterOS | `/user group add name=backup policy=ssh,read,sensitive,!write,!policy` |
| Fortinet FortiOS | A read-only admin profile can usually run `show full-configuration`; check on your version |

## Domain name

```bash
sudo bash /opt/vault/deploy/maintenance/set-domain.sh backup.example.com you@example.com
```

Needs a DNS A record to the server and ports 80 / 443 open. Issues a Let's Encrypt certificate (renewed
automatically) and keeps the IP address working.

## Checks

For fixing problems, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).


| What | Command |
|---|---|
| Service running | `systemctl status vault freeradius nginx --no-pager` |
| Application log | `sudo journalctl -u vault -n 100 --no-pager` |
| Health check | `curl -k https://127.0.0.1/healthz` → `{"status": "ok"}` |
| RADIUS users get the right level | `sudo bash /opt/vault/deploy/radius/check_levels.sh` |
| FreeRADIUS has room for a big backup run | `sudo bash /opt/vault/deploy/radius/check_capacity.sh` |
| FreeRADIUS configuration | `sudo freeradius -XC` |
| Everything after an operating-system update | `sudo bash /opt/vault/deploy/maintenance/after_os_update.sh` (read-only) |

## Operating-system updates

**Supported:** Ubuntu 22.04 and Debian 12 or newer (VAULT needs Python 3.10+; Ubuntu 20.04 and Debian 11 are too old).

- **Normal updates** (`apt upgrade`, the daily security updates) need nothing: VAULT runs in its own Python
  environment under `/opt/vault/.venv`, and its services start again by themselves after a reboot.
- **A release upgrade** (for example Ubuntu 22.04 to 24.04) replaces the system Python and may restore the
  package's own FreeRADIUS files. Afterwards run, from your VAULT git folder:

  ```bash
  git pull && sudo bash deploy/install.sh        # rebuilds the Python environment if needed, re-applies VAULT's FreeRADIUS setup
  sudo bash /opt/vault/deploy/maintenance/after_os_update.sh # read-only check: environment, services, FreeRADIUS, health
  ```

- Before a release upgrade take a VM snapshot and run `sudo bash /opt/vault/deploy/maintenance/backup_vault.sh`.

## Back up the server (disaster recovery)

```bash
sudo bash /opt/vault/deploy/maintenance/backup_vault.sh
```

Dumps both databases (`dbms`, `radius`) and copies `secret.key` / `session.key` / the SSH host-key files into
`/var/backups/vault-dr/` (add `--with-configs` to also include the saved device configuration backups). Keeps the
newest 14 days there and prints what to do next. **This alone is not enough**: that directory is on the same
disk as everything else, so copy it to another machine or off-site storage too (the script's own output shows
an `rsync` example), and add it to root's crontab for a backup every night without having to remember. Without
`secret.key`, every saved device password becomes permanently unreadable - there is no way to "reset" it.
