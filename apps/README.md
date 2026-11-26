# Apps

Every business area of VAULT is one app, and every app has the same files. Learn one, and you can read all seven.

## One file per layer

| Layer | File | Main job |
|---|---|---|
| Presentation | `views.py` (+ `urls.py`) | Receive the client's request and send the response |
| Presentation | `serializers.py` | Turn objects into JSON (passwords never leave the server) |
| Business logic | `services.py` | The rules and every change (add a device, start a backup, lock a user ...) |
| Data access | `repositories.py` | Stores that are not ordinary tables: backup files on disk, the FreeRADIUS database |
| Data access | `selectors.py` | Every database read and filter; never changes anything |
| Database | `models.py` | The tables and their fields |

```
 Browser ──HTTPS──> views.py        PRESENTATION    receive the request, check the role
                       │            serializers.py  object -> JSON
                       ▼
                    services.py     BUSINESS LOGIC  rules and every change
                       │
                       ▼
                    selectors.py    DATA ACCESS     every read
                    repositories.py                 backup files on disk, the FreeRADIUS database
                       │
                       ▼
                    models.py       DATABASE        tables and fields
                       │
                       ▼
                    MariaDB (dbms, radius)
```

Some apps have extra files for their own work:

| File | Job |
|---|---|
| `backups/jobs.py` | Background backup jobs (many devices in parallel) |
| `backups/engine.py` | SSH login to one device and read its configuration |
| `backups/reports.py` | Change report (what changed between versions) |
| `backups/audit.py` | The audit trail: who did what, when, from which address |
| `commandlog/receiver.py` | Syslog receiver on UDP 514 (service `vault-syslog`) |
| `commandlog/parsers.py` | One syslog line to a user action (Huawei, Cisco, Juniper, MikroTik, Fortinet) |
| `devices/vendors.py` | Vendor table: login driver, backup command, host-name parser |
| `monitoring/cache_keys.py` | Names of the ping cache entries |

## Example: an operator presses "Backup now"

1. `backups/views.py` checks the role (`@api(POST="operator")`) and calls the service.
2. `backups/jobs.py` starts a background job.
3. `backups/engine.py` logs in to the device over SSH and reads the configuration.
4. `backups/services.py` compares it with the last version: changed or unchanged.
5. `backups/repositories.py` saves the file; `backups/models.py` (BackupLog) records the result.

## The apps

| App | What it does |
|---|---|
| `accounts` | Portal users, sign-in, lockout, roles |
| `devices` | Device inventory and saved logins |
| `backups` | Configuration backups, versions, change reports, audit trail |
| `monitoring` | Ping monitor, Dashboard numbers, server health |
| `scheduling` | Settings and the automatic backup timer |
| `radius` | FreeRADIUS users, levels, NAS clients, Authentication Audit |
| `commandlog` | Session Log: who ran which command on which device |

`core/` (next to `apps/`) is shared by every app: the page registry, the `api()` role check, exceptions,
security headers, background tasks, encryption of device passwords and every `manage.py` command.

## The rules (checked by `python manage.py check_architecture`)

- A layer only calls the layers below it: `views.py` never touches the database, `selectors.py` never changes data.
- Another app is used only through its public files (`services.py`, `selectors.py` ...), never its `views.py` or `models.py`.
- Imports are absolute: `from apps.devices import selectors`.
