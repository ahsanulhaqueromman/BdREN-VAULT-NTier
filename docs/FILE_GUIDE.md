# File guide

Which file does what. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the big picture and the tier rules.

Every business area is one app in `apps/`, and every app has the same folders:
`api/` (HTTP), `services/` (rules and changes), `selectors/` (reads), `models/` (tables), `migrations/`,
plus `tasks/`, `integrations/` or `repositories/` where the app needs them. Shared code is in `core/`.
How to read an app: [apps/README.md](../apps/README.md).

## Where to start

| I want to change... | Open this file |
|---|---|
| The menu, a page's URL, title or who may open it | `core/pages.py` |
| A page's layout or text | `templates/<area>/<page>.html` (for example `templates/devices/index.html`) |
| The side menu, top bar or a shared pop-up | `templates/base.html`, `templates/components/` |
| What a page does (buttons, tables) | `static/js/pages/<page>.js` |
| Notifications, API calls, dates, pager | `static/js/core/helpers.js` |
| Colours, spacing, the look | `static/css/app.css` (tokens at the top); sign-in page: `static/css/auth.css` |
| Sign-in page | `templates/accounts/auth.html`, `apps/accounts/api/views.py`, `static/js/pages/auth.js` |
| Supported device types (Cisco, Huawei, Fortinet ...) | `apps/devices/vendors.py` |
| A list or number shown on a page (database read) | `apps/<app>/selectors/<app>_selectors.py` |
| A rule or a change (add, edit, delete, start) | `apps/<app>/services/<app>_service.py` |
| A table or a column | `apps/<app>/models/`, then `python manage.py makemigrations` |
| The tier rules and their check | `core/architecture.py`, `python manage.py check_architecture` |
| How a backup is taken from a device (SSH) | `apps/backups/integrations/ssh_engine.py` |
| When a backup is saved or skipped | `apps/backups/services/backup_service.py` |
| Where backup files are stored on disk | `apps/backups/repositories/backup_storage.py` |
| Background backup jobs (parallel, progress) | `apps/backups/tasks/backup_jobs.py` |
| Ping and the background ping monitor | `apps/monitoring/services/monitoring_service.py` |
| Dashboard numbers (Needs attention, recent changes, logins, health) | `apps/monitoring/selectors/monitoring_selectors.py`, `static/js/pages/dashboard.js` |
| Settings page, automatic backup timer | `apps/scheduling/services/schedule_service.py` |
| Web users, roles, sign-in lockout | `apps/accounts/services/account_service.py`, `apps/accounts/models/account.py` |
| RADIUS users, levels, NAS, audit | `apps/radius/services/radius_service.py`, `apps/radius/api/views.py` |
| FreeRADIUS policies and setup scripts | `deploy/radius/` |
| Session Log: syslog receiver, vendor message formats | `apps/commandlog/tasks/syslog_receiver.py`, `apps/commandlog/integrations/syslog_parsers.py` |
| Server settings (environment) | `config/settings/base.py` and `.env` |

## Project layout

```
config/                  Django project
  settings/              base.py: every setting, read from environment variables / .env
                         production.py: the default; development.py: DJANGO_ENV=development
  urls.py                URL table: one URL per page (from core/pages.py) + each app's api/urls.py
  wsgi.py                Entry point for waitress

core/                    Shared kernel, used by every app
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

apps/                    One app per business area; every app: api/ services/ selectors/ models/ migrations/
  accounts/              Sign-in, first-run setup, web users and roles
  devices/               Device inventory
    vendors.py           Vendor table: login driver, backup command, name parser
  backups/               Configuration backups
    services/            backup_service.py, report_service.py (change report), audit_service.py (audit trail)
    tasks/               backup_jobs.py: parallel backup jobs in a background thread
    integrations/        ssh_engine.py: SSH login to ONE device and read its configuration
    repositories/        backup_storage.py: files in data/backups/<device>/<YYYY>/<Mon>/<DD>/ (all-or-nothing)
  monitoring/            Ping and the Dashboard numbers
    cache_keys.py        Ping cache keys
  scheduling/            Settings and the automatic backup timer (no selectors/: settings are read by the service)
  radius/                RADIUS / AAA (FreeRADIUS database)
    repositories/        db_router.py: sends these tables to the second database (`radius`)
  commandlog/            Session Log (who ran which command on a device)
    tasks/               syslog_receiver.py: UDP syslog receiver (manage.py syslog_receive, service vault-syslog)
    integrations/        syslog_parsers.py: one syslog line -> user action (Huawei, Cisco, Juniper, MikroTik, Fortinet)

templates/
  base.html              Frame of every page: side menu, top bar, shared pop-ups, scripts
  components/            _page_heading.html, dialogs.html (shared pop-ups), icons/*.svg (menu icons)
  errors/forbidden.html  "You do not have access" page (HTTP 403)
  dashboard/ devices/ backups/ reports/ jobs/ logs/ accounts/ settings/ radius/   one folder per screen

static/
  css/app.css            Application styles (design tokens first, then layout, components, pages, responsive)
  css/auth.css           Sign-in page styles
  js/core/               Shared by every page (see ARCHITECTURE.md, "Browser code")
  js/pages/              One file per page
  img/vendors/           Vendor logos

deploy/                  Server scripts (the ones you run are at the top level)
  install.sh             One command: install a new server or update an existing one
  uninstall.sh           Remove VAULT from a server
  backup_vault.sh        Back up the databases, keys and settings before an update
  after_os_update.sh     Read-only health check after an Ubuntu / Debian upgrade
  harden.sh              Firewall, login rate limit, automatic security updates (install.sh runs it)
  set-domain.sh          Add a domain name with a Let's Encrypt certificate
  enable_syslog.sh       Install / repair the syslog receiver (install.sh runs it)
  systemd/               vault.service (web app), vault-syslog.service (Session Log receiver)
  nginx/                 nginx-dbms.conf: the HTTPS site in front of the app
  radius/                FreeRADIUS policies, enable_*.sh helpers, check_levels.sh (RADIUS health check)
  build/                 build_release.py (release zip), build_compiled.sh (build without .py sources)

docs/                    ARCHITECTURE, FILE_GUIDE (this file), CONTRIBUTING, DEPLOY, TROUBLESHOOTING
```

## The tiers inside every app

| Tier | Folder | Job |
|---|---|---|
| 1. Presentation | `apps/<app>/api/`, `core/pages.py`, `templates/`, `static/`, `deploy/nginx/` | Screens, JSON answers, HTTPS |
| 2. Business | `apps/<app>/services/`, `tasks/`, `core/background.py` | Rules, changes, background work |
| 3. Data access | `apps/<app>/selectors/`, `repositories/`, `integrations/` | Reads, files, SSH, syslog |
| 4. Entities | `apps/<app>/models/`, `migrations/` | Tables in MariaDB `dbms` and `radius` |

`python manage.py check_architecture` makes sure a tier only calls the tiers below it.

## Scripts and their order

`templates/base.html` loads, in this order: `core/helpers.js`, `core/menu.js`, `core/account.js`,
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

- Migrations (`apps/*/migrations/`) are generated by Django; do not edit or delete them.
- `logs/`, `data/`, `staticfiles/` and `__pycache__/` are created at run time; they are not source code.
- After changing a CSS or JS file, raise every `?v=` number in `templates/base.html` (and in
  `templates/accounts/auth.html` for the sign-in files) so browsers load the new version.
- Templates are cached in production: restart the service (`sudo systemctl restart vault`) after changing one.
