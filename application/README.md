# Tier 2 - Application

The rules and the work: every decision, every change, every read, the SSH backup engine, the syslog
receiver and the background tasks.

**Rules** (checked by `python manage.py check_architecture`):

- This tier uses `persistence/` below it, never `presentation/` above it.
- `selectors.py` only reads; it never imports `services.py`.
- Another area is used only through its public modules (`selectors`, `services`, `audit`, `vendors`, `jobs`, `engine` ...).
  Example: the Dashboard reads backup numbers with `application.backups.selectors`, never `BackupLog.objects`.
- Raise `application.core.errors.ApiError(400, "message")` to show an error to the user.

## The two main files of every area

| File | Job | Example |
|---|---|---|
| `services.py` | Rules and every change: validation, writes, transactions | add a device, start a backup, lock a user |
| `selectors.py` | Every database read; changes nothing | device list, Dashboard numbers, Session Log cards |

## Folders

| Folder | Files | Job |
|---|---|---|
| `core/` | `errors.py` | `ApiError`, shown to the browser as `{"error": ...}` |
| | `background.py` | Starts the scheduler, ping monitor and clean-up threads (composition root) |
| | `architecture.py` | The tier rules behind `check_architecture` |
| | `netguard.py` | Which addresses SSH and ping may reach |
| | `alerts.py` | E-mail / Telegram alert on a failed backup |
| | `summary_report.py` | The PDF summary report |
| | `utils.py`, `period.py` | Date formats, CSV safety, report periods |
| `accounts/` | `services.py`, `selectors.py` | Password rules, lockout, users, sign-in history |
| `devices/` | `services.py`, `selectors.py` | Device inventory, saved logins |
| | `vendors.py` | Vendor table: login driver, backup command, host-name parser |
| `backups/` | `services.py`, `selectors.py` | Back up one device, versions, retention |
| | `engine.py` | SSH login to ONE device and read its configuration |
| | `storage.py` | Snapshot files in `data/backups/` (all-or-nothing saves, checksums) |
| | `jobs.py` | Parallel backup jobs in a background thread |
| | `reports.py` | Change report (diff of versions per month range) |
| | `audit.py` | The audit trail: `record_audit()` and its reads |
| `monitoring/` | `services.py`, `selectors.py`, `keys.py` | Ping, background monitor, Dashboard numbers, server health |
| `scheduling/` | `services.py` | Settings and the automatic backup timer |
| `radius/` | `services.py`, `selectors.py` | FreeRADIUS users, levels, NAS, password hashing, Authentication Audit |
| `commandlog/` | `services.py`, `selectors.py` | Session Log: saving events, building sessions |
| | `receiver.py` | UDP syslog receiver (service `vault-syslog`) |
| | `parsers.py` | One syslog line to a user action (Huawei, Cisco, Juniper, MikroTik, Fortinet) |
| `management/commands/` | | Every `python manage.py ...` command (below) |

## Commands (`management/commands/`)

| Command | Job |
|---|---|
| `serve` | Runs the web server (Waitress) with the scheduler and ping monitor (service `vault`) |
| `syslog_receive` | Runs the Session Log syslog receiver (service `vault-syslog`) |
| `run_background` | Runs only the scheduler and ping monitor, without a web server |
| `check_architecture` | Checks the tier rules |
| `system_health` | Read-only checks: database, keys, backup folder, disk space |
| `verify_backups` | Read-only check of every saved backup against its SHA-256 file |
| `backup_retention` | Lists old snapshots (dry run); `--apply` deletes them, keeping each device's latest |
| `configure_auto_backup` | Turns on the automatic backup schedule for all devices |
| `show_network_policy` | Shows which device networks VAULT may SSH to |
| `radius_init` | Prepares an existing FreeRADIUS database for the RADIUS pages |
| `radius_hash_passwords` | Turns clear-text RADIUS passwords into salted SHA-256 (same passwords) |
| `seed_groups` | Creates or refreshes the super-admin, read-write and read-only RADIUS groups |

`apps.py` registers this folder with Django only so the commands are found.
