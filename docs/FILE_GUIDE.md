# File guide

Which file does what. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the big picture and the tier rules.

The code is split into four tiers (top-level folders); inside each tier is one folder per app:

| Tier | Folder | Files | Main job |
|---|---|---|---|
| 1 Presentation | `presentation/<app>/` | `views.py`, `urls.py`, `serializers.py` (+ `presentation/templates/`, `presentation/static/`) | Receive the request, send the response; passwords never leave the server |
| 2 Business logic | `business/<app>/` | `services.py` (+ `backup_jobs.py`, `change_reports.py`, `syslog_receiver.py`) | The rules and every change (add a device, start a backup, lock a user ...) |
| 3 Data access | `data_access/<app>/` | `selectors.py`, `repositories.py` (+ `ssh_client.py`, `audit_log.py`, `syslog_parsers.py`, `vendor_registry.py`, `cache_keys.py`) | Every read; backup files on disk; the FreeRADIUS database; SSH to devices |
| 4 Database | `database/<app>/` | `models.py`, `migrations/`, `apps.py`, `admin.py` | The tables and their fields |

Shared code is in `core/`. Each tier folder has a short README.

## Where to start

| I want to change... | Open this file |
|---|---|
| The menu, a page's URL, title or who may open it | `core/pages.py` |
| A page's layout or text | `presentation/templates/<area>/<page>.html` (for example `presentation/templates/devices/index.html`) |
| The side menu, top bar or a shared pop-up | `presentation/templates/base.html`, `presentation/templates/components/` |
| What a page does (buttons, tables) | `presentation/static/js/pages/<page>.js` |
| Notifications, API calls, dates, pager | `presentation/static/js/core/helpers.js` |
| Colours, spacing, the look | `presentation/static/css/app.css` (tokens at the top); sign-in page: `presentation/static/css/auth.css` |
| Sign-in page | `presentation/templates/accounts/auth.html`, `presentation/accounts/views.py`, `presentation/static/js/pages/auth.js` |
| Supported device types (Cisco, Huawei, Fortinet ...) | `data_access/devices/vendor_registry.py` |
| A list or number shown on a page (database read) | `data_access/<app>/selectors.py` |
| A rule or a change (add, edit, delete, start) | `business/<app>/services.py` |
| A table or a column | `database/<app>/models.py`, then `python manage.py makemigrations` |
| The tier rules and their check | `core/architecture.py`, `python manage.py check_architecture` |
| How a backup is taken from a device (SSH) | `data_access/backups/ssh_client.py` |
| When a backup is saved or skipped | `business/backups/services.py` |
| Where backup files are stored on disk | `data_access/backups/repositories.py` |
| Background backup jobs (parallel, progress) | `business/backups/backup_jobs.py` |
| Ping and the background ping monitor | `business/monitoring/services.py` |
| Dashboard numbers (Needs attention, recent changes, logins, health) | `data_access/monitoring/selectors.py`, `presentation/static/js/pages/dashboard.js` |
| Settings page, automatic backup timer | `business/scheduling/services.py` |
| Web users, roles, sign-in lockout | `business/accounts/services.py`, `database/accounts/models.py` |
| RADIUS users, levels, NAS, audit | `business/radius/services.py`, `presentation/radius/views.py` |
| FreeRADIUS policies and setup scripts | `deploy/radius/` |
| Session Log: syslog receiver, vendor message formats | `business/commandlog/syslog_receiver.py`, `data_access/commandlog/syslog_parsers.py` |
| Server settings (environment) | `config/settings/base.py` and `.env` |

## Project layout

```
config/                  Django project
  settings/              base.py: every setting, read from environment variables / .env
                         production.py: the default; development.py: DJANGO_ENV=development
  urls.py                URL table: one URL per page (from core/pages.py) + each app's presentation/<app>/urls.py
  wsgi.py                Entry point for waitress

core/                    Shared kernel, used by every tier
  pages.py               THE PAGE REGISTRY: every screen, its URL, menu group, template, icon and role
  views.py               Renders a page (base.html + the page's template), /healthz, /robots.txt
  api.py                 @api(...) decorator: method and role check for every JSON endpoint
  exceptions.py          ApiError: raised anywhere, shown to the browser as {"error": ...}
  middleware.py          Security headers on every response
  background.py          Composition root: starts the scheduler, ping monitor and clean-up threads
  crypto.py, keys.py     Device-password encryption (Fernet) and key files
  netguard.py            Which addresses SSH and ping may reach
  alerts.py              Optional e-mail / Telegram alerts for failed backups
  summary_report.py      The PDF summary report
  utils.py, period.py    Date formats, CSV safety, report periods
  architecture.py        The tier rules (python manage.py check_architecture)
  management/commands/   serve, syslog_receive, check_architecture, verify_backups, system_health,
                         backup_retention, radius_init, radius_hash_passwords, ...

presentation/            TIER 1: one folder per app with views.py (+ urls.py)
  devices/serializers.py Device -> JSON (passwords replaced by yes/no flags)
  templates/
    base.html            Frame of every page: side menu, top bar, shared pop-ups, scripts
    components/          _page_heading.html, dialogs.html (shared pop-ups), icons/*.svg (menu icons)
    errors/forbidden.html  "You do not have access" page (HTTP 403)
    dashboard/ devices/ backups/ reports/ jobs/ logs/ accounts/ settings/ radius/   one folder per screen

business/                TIER 2: one folder per app with services.py
  backups/backup_jobs.py        Parallel backup jobs in a background thread (second pass, retry queue)
  backups/change_reports.py     Change report (diff of versions per month range)
  commandlog/syslog_receiver.py UDP syslog receiver (manage.py syslog_receive, service vault-syslog)

data_access/             TIER 3: one folder per app with selectors.py
  devices/vendor_registry.py     Vendor table: login driver, backup command, name parser
  backups/repositories.py  Backup files in data/backups/<device>/<YYYY>/<Mon>/<DD>/ (all-or-nothing saves)
  backups/ssh_client.py      SSH login to ONE device and read its configuration
  backups/audit_log.py       The audit trail: record_audit() and its reads
  radius/repositories.py Sends the FreeRADIUS tables to the second database (`radius`)
  commandlog/syslog_parsers.py  One syslog line -> user action (Huawei, Cisco, Juniper, MikroTik, Fortinet)
  monitoring/cache_keys.py  Ping cache keys

database/                TIER 4: one folder per app with models.py, migrations/, apps.py, admin.py
  accounts/ devices/ backups/ scheduling/ monitoring/ radius/ commandlog/

presentation/static/      (part of TIER 1)
  css/app.css            Application styles (design tokens first, then layout, components, pages, responsive)
  css/auth.css           Sign-in page styles
  js/core/               Shared by every page (see ARCHITECTURE.md, "Browser code")
  js/pages/              One file per page
  img/vendors/           Vendor logos

deploy/                  Server scripts (table with every script: deploy/README.md)
  install.sh             One command: install a new server or update an existing one
  uninstall.sh           Remove VAULT from a server
  maintenance/           backup_vault.sh (back up before an update), after_os_update.sh (read-only check),
                         harden.sh (firewall, rate limit), set-domain.sh (Let's Encrypt), enable_syslog.sh
  systemd/               vault.service (web app), vault-syslog.service (Session Log receiver)
  nginx/                 nginx-dbms.conf: the HTTPS site in front of the app
  radius/                FreeRADIUS policies, enable_*.sh helpers, check_levels.sh (RADIUS health check)
  build/                 build_release.py (release zip), build_compiled.sh (build without .py sources)

docs/                    ARCHITECTURE, FILE_GUIDE (this file), CONTRIBUTING, DEPLOY, TROUBLESHOOTING
```

## The tier rules

presentation → business → data_access → database: a tier only uses the tiers below it, the presentation tier
never queries the database, and `core/` never uses presentation. `python manage.py check_architecture` checks it.

## Scripts and their order

`presentation/templates/base.html` loads, in this order: `core/helpers.js`, `core/menu.js`, `core/account.js`,
`pages/dashboard.js`, `pages/devices.js`, `core/backup-jobs.js`, `pages/backups.js`, `pages/logs.js`,
`pages/users.js`, `pages/settings.js`, `pages/radius.js`, `pages/commands.js`, `pages/reports.js`, `pages/jobs.js`, `core/search.js`,
`core/start.js` (must come after every page loader), `core/responsive.js`.

| Page script | Page | Loader in `PAGE_INIT` |
|---|---|---|
| `dashboard.js` | Dashboard | `loadDashboard` |
| `devices.js` | Device Inventory (table, filters, ping, Add / Edit pop-ups, saved logins) | `loadDevices` |
| `backups.js` | Configuration Backups, one device's page, the viewer / compare pop-up | `loadBackups`, `loadDevicePage` |
| `reports.js` | Change Reports (month range, PDF / CSV) | `loadReport` |
| `jobs.js` | Backup Jobs | `loadJobs` |
| `logs.js` | Activity Logs and the audit trail | `loadLogs` |
| `users.js` | User Management and sign-in history | `loadUsers` |
| `settings.js` | System Settings and the capacity planner | `loadSettings` |
| `radius.js` | AAA Users, NAS Clients, Authentication Audit, Device Setup | `loadRadUsers`, `loadRadNas`, `loadRadAudit`, `loadRadSetup` |
| `commands.js` | Session Log | `loadCommands` |

## Things to know

- Migrations (`database/*/migrations/`) are generated by Django; do not edit or delete them.
- `logs/`, `data/`, `staticfiles/` and `__pycache__/` are created at run time; they are not source code.
- After changing a CSS or JS file, raise every `?v=` number in `presentation/templates/base.html` (and in
  `presentation/templates/accounts/auth.html` for the sign-in files) so browsers load the new version.
- Templates are cached in production: restart the service (`sudo systemctl restart vault`) after changing one.
