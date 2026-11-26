# File guide

Which file does what. Read [ARCHITECTURE.md](ARCHITECTURE.md) first for the big picture and the tier rules.

The code is split into three tiers, one top-level folder each, and every area (accounts, devices,
backups, ...) has its own folder inside each tier:

- `presentation/<area>/` - `views.py` + `urls.py` (HTTP), plus `presentation/templates/` and `presentation/static/`
- `application/<area>/` - `services.py` (rules and changes), `selectors.py` (reads), integrations (SSH, files, jobs ...)
- `persistence/<area>/` - `models.py` (tables), `migrations/`, `apps.py` (the Django app)

## Where to start

| I want to change... | Open this file |
|---|---|
| The menu, a page's URL, title or who may open it | `presentation/core/pages.py` |
| A page's layout or text | `presentation/templates/<area>/<page>.html` (for example `presentation/templates/devices/index.html`) |
| The side menu, top bar or a shared pop-up | `presentation/templates/base.html`, `presentation/templates/components/` |
| What a page does (buttons, tables) | `presentation/static/js/pages/<page>.js` |
| Notifications, API calls, dates, pager | `presentation/static/js/core/helpers.js` |
| Colours, spacing, the look | `presentation/static/css/app.css` (tokens at the top); sign-in page: `presentation/static/css/auth.css` |
| Sign-in page | `presentation/templates/accounts/auth.html`, `presentation/accounts/views.py`, `presentation/static/js/pages/auth.js` |
| Supported device types (Cisco, Huawei, Fortinet ...) | `application/devices/vendors.py` |
| A list or number shown on a page (database read) | `application/<area>/selectors.py` |
| A rule or a change (add, edit, delete, start) | `application/<area>/services.py` |
| A table or a column | `persistence/<area>/models.py`, then `python manage.py makemigrations` |
| The tier rules and their check | `application/core/architecture.py`, `python manage.py check_architecture` |
| How a backup is taken from a device (SSH) | `application/backups/engine.py` |
| When a backup is saved or skipped | `application/backups/services.py` |
| Where backup files are stored on disk | `application/backups/storage.py` |
| Background backup jobs (parallel, progress) | `application/backups/jobs.py` |
| Ping and the background ping monitor | `application/monitoring/services.py` |
| Dashboard numbers (Needs attention, recent changes, logins, health) | `application/monitoring/selectors.py`, `presentation/static/js/pages/dashboard.js` |
| Settings page, automatic backup timer | `application/scheduling/services.py` |
| Web users, roles, sign-in lockout | `application/accounts/services.py`, `persistence/accounts/models.py` |
| RADIUS users, levels, NAS, audit | `application/radius/services.py`, `presentation/radius/views.py` |
| FreeRADIUS policies and setup scripts | `deploy/radius/` |
| Session Log: syslog receiver, vendor message formats | `application/commandlog/receiver.py`, `application/commandlog/parsers.py` |
| Server settings (environment) | `config/settings.py` and `.env` |

## Project layout

```
config/                  Django project
  settings.py            All settings, read from environment variables / .env
  urls.py                URL table: one URL per page (from presentation/core/pages.py) + each area's /api/ URLs
  wsgi.py                Entry point for waitress

presentation/            TIER 1 - what the user sees
  core/
    pages.py             THE PAGE REGISTRY: every screen, its URL, menu group, template, icon and role
    views.py             Renders a page (base.html + the page's template), /healthz, /robots.txt
    api.py               @api(...) decorator: method and role check for every JSON endpoint
    middleware.py        Security headers on every response
  accounts/ devices/ backups/ monitoring/ scheduling/ radius/ commandlog/
                         views.py + urls.py of each area (JSON API and pages)
  templates/
    base.html            Frame of every page: side menu, top bar, shared pop-ups, scripts
    components/          _page_heading.html, dialogs.html (shared pop-ups), icons/*.svg (menu icons)
    errors/forbidden.html  "You do not have access" page (HTTP 403)
    dashboard/ devices/ backups/ reports/ jobs/ logs/ accounts/ settings/ radius/   one folder per screen
  static/
    css/app.css          Application styles (design tokens first, then layout, components, pages, responsive)
    css/auth.css         Sign-in page styles
    js/core/             Shared by every page (see ARCHITECTURE.md, "Browser code")
    js/pages/            One file per page
    img/vendors/         Vendor logos

application/             TIER 2 - rules and work
  core/
    errors.py            ApiError: raised anywhere, shown to the browser as {"error": ...}
    background.py        Composition root: starts the scheduler, ping monitor and log retention threads
    architecture.py      The tier rules (python manage.py check_architecture)
    netguard.py          Checks SSH target addresses
    alerts.py            Optional e-mail / Telegram alerts for failed backups
    utils.py, period.py  Date formats, CSV safety, report periods
    summary_report.py    The PDF summary report
  accounts/              services.py (password rules, lockout)  selectors.py (users, sign-in history)
  devices/               services.py  selectors.py
    vendors.py           Vendor table: login driver, backup command, name parser
  backups/               services.py  selectors.py
    engine.py            SSH login to ONE device and read its configuration
    storage.py           Snapshot files: data/backups/<device>/<YYYY>/<Mon>/<DD>/ (all-or-nothing saves)
    jobs.py              Parallel backup jobs in a background thread
    reports.py           Change report (diff of versions per month range)
    audit.py             The audit trail: record_audit() and every audit read
  monitoring/            services.py (ping, monitor)  selectors.py (Dashboard, health)  keys.py (ping cache keys)
  scheduling/            services.py (settings and the automatic backup timer)
  radius/                services.py  selectors.py (FreeRADIUS users, levels, NAS, audit)
  commandlog/            services.py  selectors.py (Session Log)
    parsers.py           One syslog line -> user action (Huawei, Cisco, Juniper, MikroTik, Fortinet)
    receiver.py          UDP syslog receiver (manage.py syslog_receive, service vault-syslog)
  management/commands/   serve, syslog_receive, check_architecture, backup_retention, verify_backups,
                         system_health, radius_init, radius_hash_passwords, ...
  apps.py                Registers this tier with Django so the commands are found

persistence/             TIER 3 - data
  core/
    crypto.py, keys.py   Device-password encryption (Fernet) and key files
  accounts/ devices/ backups/ monitoring/ scheduling/ radius/ commandlog/
    apps.py              The Django app of the area (label unchanged, so tables and migrations stay the same)
    models.py            Tables
    migrations/          Database changes, generated by Django
    admin.py             Django admin registration (where present)
  radius/router.py       Sends the RADIUS tables to the second database (`radius`)

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

## The same layout by tier

VAULT is a three-tier application, and the folders follow the tiers:

| Tier | Folders and files | Job |
|---|---|---|
| 1. Presentation | `presentation/` (views, urls, api, middleware, pages, templates, static), `deploy/nginx/` | Screens, JSON answers, HTTPS |
| 2. Application | `application/` (services, selectors, engine, jobs, parsers, receiver, background, commands) | Rules, backups, syslog, background work |
| 3. Data | `persistence/` (models, migrations, router, crypto), `data/` (not in Git) | Tables in MariaDB `dbms` and `radius`, backup files, keys |
| Around them | `config/` (settings), `deploy/` (install and run), `docs/` | Setup and operation |

`python manage.py check_architecture` makes sure a tier only calls the tier below it.

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

- Migrations (`persistence/*/migrations/`) are generated by Django; do not edit or delete them.
- `logs/`, `data/`, `staticfiles/` and `__pycache__/` are created at run time; they are not source code.
- After changing a CSS or JS file, raise every `?v=` number in `presentation/templates/base.html` (and in
  `presentation/templates/accounts/auth.html` for the sign-in files) so browsers load the new version.
- Templates are cached in production: restart the service (`sudo systemctl restart vault`) after changing one.
