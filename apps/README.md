# Domain apps

Every business area of VAULT is one app, and every app is built the same way. Learn one, and you can read all seven.

## The four tiers inside an app

```
 Browser  ──HTTPS──>  api/            1. PRESENTATION   views.py, urls.py
                         │                               reads the request, checks the role, answers in JSON
                         ▼
                      services/       2. BUSINESS       <app>_service.py
                         │                               rules and every change (validation, writes, transactions)
                         ▼
                      selectors/      3. DATA ACCESS    <app>_selectors.py
                         │                               every database read; never changes anything
                         ▼
                      models/         4. ENTITIES       the tables
                         │
                         ▼
                      MariaDB  (dbms, radius)
```

Some apps also have:

| Folder | Job | Where |
|---|---|---|
| `tasks/` | Work that runs in the background | `backups/tasks/backup_jobs.py` (parallel backups), `commandlog/tasks/syslog_receiver.py` (UDP 514) |
| `integrations/` | Talking to the outside world | `backups/integrations/ssh_engine.py` (SSH to devices), `commandlog/integrations/syslog_parsers.py` (vendor log formats) |
| `repositories/` | Data that is not a normal table | `backups/repositories/backup_storage.py` (backup files on disk), `radius/repositories/db_router.py` (the FreeRADIUS database) |

## Example: an operator presses "Backup now" on a device

1. `apps/backups/api/views.py` checks the role (`@api(POST="operator")`) and calls the service.
2. `apps/backups/tasks/backup_jobs.py` starts a background job.
3. `apps/backups/integrations/ssh_engine.py` logs in to the device over SSH and reads the configuration.
4. `apps/backups/services/backup_service.py` compares it with the last version and decides: changed or unchanged.
5. `apps/backups/repositories/backup_storage.py` saves the file; `apps/backups/models/backup.py` records the result.

## The apps

| App | What it does | Main files |
|---|---|---|
| `accounts` | Portal users, sign-in, lockout, roles | `services/account_service.py`, `models/account.py` |
| `devices` | Device inventory and saved logins | `services/device_service.py`, `vendors.py` |
| `backups` | Configuration backups, versions, reports, audit trail | `services/backup_service.py`, `tasks/backup_jobs.py`, `integrations/ssh_engine.py` |
| `monitoring` | Ping monitor, Dashboard numbers, server health | `services/monitoring_service.py`, `selectors/monitoring_selectors.py` |
| `scheduling` | Settings and the automatic backup timer | `services/schedule_service.py` |
| `radius` | FreeRADIUS users, levels, NAS clients, Authentication Audit | `services/radius_service.py`, `repositories/db_router.py` |
| `commandlog` | Session Log: who ran which command on which device | `tasks/syslog_receiver.py`, `integrations/syslog_parsers.py` |

`core/` (next to `apps/`) is shared by every app: the page registry, the `api()` role check, exceptions,
security headers, background tasks, encryption of device passwords and every `manage.py` command.

## The rules (checked by `python manage.py check_architecture`)

- A tier only calls the tiers below it: `api/` never touches the database, `selectors/` never changes data.
- Another app is used only through its `services/` or `selectors/`, never its `api/` or `models/`.
- Imports are absolute: `from apps.devices.selectors import device_selectors`.
