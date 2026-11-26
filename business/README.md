# Tier 2 - Business logic

The rules and every change: add a device, start a backup, lock a user, save the settings.

| File | Main job |
|---|---|
| `<app>/services.py` | Validation, writes, transactions (one per app) |
| `backups/backup_jobs.py` | Background backup jobs (many devices in parallel, second pass, retry queue) |
| `backups/change_reports.py` | Change report (what changed between versions) |
| `commandlog/syslog_receiver.py` | Syslog receiver on UDP 514 (service `vault-syslog`) |

Rules: may use `data_access` and `database`, never `presentation`.
