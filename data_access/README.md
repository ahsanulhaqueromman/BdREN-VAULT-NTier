# Tier 3 - Data access

Every read, the stores that are not ordinary tables, and the outside world. Selectors never change data.

| File | Main job |
|---|---|
| `<app>/selectors.py` | Every database read and filter (one per app) |
| `backups/repositories.py` | Backup files on disk (save, read, verify) |
| `radius/repositories.py` | The second (FreeRADIUS) database and its router |
| `backups/audit.py` | The audit trail: who did what, when, from which address |
| `backups/engine.py` | SSH login to one device and read its configuration |
| `commandlog/parsers.py` | One syslog line to a user action (Huawei, Cisco, Juniper, MikroTik, Fortinet) |
| `devices/vendors.py` | Vendor table: login driver, backup command, host-name parser |
| `monitoring/cache_keys.py` | Names of the ping cache entries |

Rules: may use `database`, never `business` or `presentation`.
