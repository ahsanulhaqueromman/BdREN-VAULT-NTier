# Deploy scripts

Everything needed to install, run and look after VAULT on a Linux server (Ubuntu 22.04+ / Debian 12+).
Run every script with `sudo` from the installed folder (`/opt/vault` unless you chose another `APP_DIR`).

## Folders

| Folder / file | Kind | Main job |
|---|---|---|
| `install.sh` | Install | Install a new server or update an existing one (one command, safe to run again) |
| `uninstall.sh` | Install | Remove VAULT from a server (asks first; `--yes` skips the question) |
| `maintenance/` | Maintenance | Scripts for looking after a running server (below) |
| `systemd/` | Service | `vault.service` (web application), `vault-syslog.service` (Session Log receiver) |
| `nginx/` | Web server | `nginx-dbms.conf`: the HTTPS site in front of the application |
| `radius/` | FreeRADIUS | Policies (`dbms_device_limit`, `dbms_dynamic_clients`, `dbms_huawei_levels`) and their setup / check scripts |
| `build/` | Build | `build_release.py` (release zip), `build_compiled.sh` (package without readable `.py` files) |

## Maintenance scripts (`maintenance/`)

| Script | When to run | What it does |
|---|---|---|
| `backup_vault.sh` | Before every update, and nightly | Backs up both databases, the keys and settings to `/var/backups/vault-dr/` (`--with-configs` adds the saved configurations) |
| `after_os_update.sh` | After an Ubuntu / Debian upgrade | Read-only check: Python environment, services, FreeRADIUS configuration, health page |
| `harden.sh` | Run by `install.sh`; again after a fix | Firewall, sign-in rate limit, automatic security updates |
| `set-domain.sh` | When the server gets a domain name | HTTPS certificate from Let's Encrypt for that name |
| `enable_syslog.sh` | Run by `install.sh`; again after changing `SYSLOG_PORT` | Installs or repairs the Session Log syslog receiver |

## Usual order

```bash
sudo APP_DIR=/opt/vault bash /opt/vault/deploy/maintenance/backup_vault.sh --with-configs   # 1. back up
cd /path/to/clone && git pull                                                            # 2. new code
sudo bash deploy/install.sh                                                              # 3. install / update
sudo bash /opt/vault/deploy/maintenance/after_os_update.sh                               # 4. check (read-only)
```

The FreeRADIUS scripts in `radius/` are described in [docs/DEPLOY.md](../docs/DEPLOY.md) and
[docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md).
