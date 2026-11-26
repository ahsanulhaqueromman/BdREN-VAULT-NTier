# Architecture

How the VAULT is put together. For "which file does what", see
[FILE_GUIDE.md](FILE_GUIDE.md); to add or change something, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Components

```
 Browser ──HTTPS──> nginx :443 ──> waitress (manage.py serve, service "vault") ──> Django app
                                                                                  │
            ┌──────────────────────────────┬──────────────────────────┬──────────┴─────────────┐
            │ MySQL "dbms"                  │ MySQL "radius"            │ data/ folder            │
            │ devices, jobs, logs, users,   │ FreeRADIUS tables: users, │ backups/ (snapshots)    │
            │ settings, audit               │ groups, NAS, login log    │ secret.key, known_hosts │
            └──────────────────────────────┴─────────────┬────────────┴────────────────────────┘
                                                         │ read on every login
 Switch / router ──RADIUS UDP 1812──> FreeRADIUS 3 ──────┘
 Switch / router ──syslog UDP 514───> syslog receiver (manage.py syslog_receive, service "vault-syslog")
                                      ──> MySQL "dbms" (Session Log)
 Backup engine ──SSH 22 / ICMP──> switches, routers, OLTs, firewalls
```

- **Django app** (one process): web pages, JSON API, the SSH backup engine, the scheduler and the ping monitor
  (background threads started by `core/background.py`).
- **Syslog receiver** (its own process): turns the devices' syslog into Session Log logins, commands and
  changes. It accepts only NAS Clients addresses, at most 200 messages a second per device.
- **FreeRADIUS** never talks to the app. Both use the `radius` database, so a user, level, device limit or new
  switch saved in the panel is used on the next login, with no restart.

## Layered architecture (server)

The code is split into four tiers, one top-level folder each. Inside every tier there is one folder per app
(`accounts`, `devices`, `backups`, `scheduling`, `monitoring`, `radius`, `commandlog`). A tier may only use the
tiers **below** it:

```
 presentation/<app>/    TIER 1  PRESENTATION    read the request → call business / data access → answer (JSON / page)
   views.py urls.py                             + record the audit entry (it needs the request: user and IP)
   serializers.py                               object → JSON (passwords never leave the server)
   templates/ static/                           HTML, CSS, JavaScript
     │
     ▼
 business/<app>/        TIER 2  BUSINESS LOGIC  rules and every change: validation, writes, transactions
   services.py                                  + background work: jobs.py (backup jobs), receiver.py (syslog)
     │
     ▼
 data_access/<app>/     TIER 3  DATA ACCESS     every database read; selectors never change anything
   selectors.py                                 + repositories.py (backup files, the radius database),
   repositories.py                                engine.py (SSH), parsers.py (syslog formats), audit.py
     │
     ▼
 database/<app>/        TIER 4  DATABASE        tables and fields only
   models.py migrations/
```

| Tier | Folder | Files | Main job |
|---|---|---|---|
| 1 Presentation | `presentation/<app>/` | `views.py`, `urls.py`, `serializers.py` (+ `presentation/templates/`, `presentation/static/`) | Receive the request, send the response; passwords never leave the server |
| 2 Business logic | `business/<app>/` | `services.py` (+ `jobs.py`, `reports.py`, `receiver.py`) | The rules and every change (add a device, start a backup, lock a user ...) |
| 3 Data access | `data_access/<app>/` | `selectors.py`, `repositories.py` (+ `engine.py`, `audit.py`, `parsers.py`, `vendors.py`, `cache_keys.py`) | Every read; backup files on disk; the FreeRADIUS database; SSH to devices |
| 4 Database | `database/<app>/` | `models.py`, `migrations/`, `apps.py`, `admin.py` | The tables and their fields |

One feature is always found the same way: `presentation/devices/views.py` → `business/devices/services.py`
→ `data_access/devices/selectors.py` → `database/devices/models.py`. Each tier folder has its own README.

| App | presentation: views.py | business: services.py | data_access: selectors.py | other files |
|---|---|---|---|---|
| `accounts` | sign-in pages, `/api/me`, `/api/users` | password rules, lockout, user changes | users, sign-in history | |
| `devices` | `/api/devices`, `/api/credentials` | validation, add / edit / delete, saved logins | inventory, saved login profiles | |
| `backups` | `/api/backup`, `/api/jobs`, `/api/logs`, `/api/backups` | back up one device, start / stop jobs, delete versions, log housekeeping | jobs, logs, versions, reports, alerts | `engine.py`, `repositories.py`, `audit.py` (data_access); `jobs.py`, `reports.py` (business) |
| `monitoring` | `/api/ping`, `/api/dashboard` | ping, background monitor | Dashboard numbers, server health | OS `ping` |
| `scheduling` | `/api/settings` | settings, the backup timer | stored settings, retry queue, next run | |
| `radius` | `/api/radius/*` | RADIUS users, levels, NAS, FreeRADIUS restart, password hashing, NAS names from syslog | users, NAS, logins, limit violations | `repositories.py` (second database, data_access) |
| `commandlog` | `/api/radius/commands*` | save what the receiver hands over, dismiss a warning, clean-up | sessions, devices sending logs, receiver state, From for Authentication Audit | `receiver.py` (UDP 514, business), `parsers.py` (vendor formats, data_access) |
| `core` | pages, `/healthz`, `api.py`, `middleware.py` | | | `exceptions.py`, `netguard.py`, `background.py`; persistence: `crypto.py`, `keys.py` |

**Between apps** the same tier rule applies: the Dashboard (`data_access/monitoring/selectors.py`) reads
backup numbers with `data_access.backups.selectors.results_per_day()`; the presentation tier never touches
`BackupLog.objects`. `core/` is the shared kernel every tier may use (but core never uses presentation); `core/background.py` is the composition root that starts the periodic services.
Maintenance commands (`core/management/commands/`) may use any app's models directly, like migrations.

**The rules are checked by a command**, so they cannot drift:

```bash
python manage.py check_architecture        # "Architecture OK" or the file, line and rule broken
```

The rules themselves are in `core/architecture.py`; the test suite runs the same check.

## Pages: one URL per screen

Every screen is its own page. The list lives in one place, **`core/pages.py`**:

| Key | URL | Template | Role |
|---|---|---|---|
| `dashboard` | `/dashboard` | `dashboard/index.html` | Viewer |
| `devices` | `/devices` | `devices/index.html` | Viewer |
| `device` | `/devices/<id>` | `devices/detail.html` | Viewer |
| `backups` | `/backups` | `backups/index.html` | Viewer |
| `reports` | `/reports` | `reports/index.html` | Viewer |
| `jobs` | `/jobs` | `jobs/index.html` | Viewer |
| `logs` | `/logs` | `logs/index.html` | Viewer |
| `radius-users` | `/radius/users` | `radius/users.html` | Administrator |
| `radius-nas` | `/radius/nas` | `radius/nas.html` | Administrator |
| `radius-audit` | `/radius/audit` | `radius/audit.html` | Administrator |
| `radius-commands` | `/radius/commands` | `radius/commands.html` (Session Log) | Administrator |
| `radius-setup` | `/radius/setup` | `radius/setup.html` (Device Setup) | Administrator |
| `users` | `/users` | `accounts/users.html` | Administrator |
| `settings` | `/settings` | `settings/index.html` | Administrator |

The registry drives the URL table (`config/urls.py`), the side menu, the breadcrumb, the browser-tab title and
access. A role below the page's role gets `presentation/templates/errors/forbidden.html` (HTTP 403). `/` opens the Dashboard;
after signing in the user returns to the page they asked for (`/login?next=/devices`).

### Request flow of a page

1. `core/views.py: page_view()` looks the key up in the registry and renders the page's template.
2. Every page template does `{% extends "base.html" %}` and fills `{% block content %}`.
3. `presentation/templates/base.html` draws the side menu (for this role), top bar, shared pop-ups, and sets
   `<body data-page="devices" class="r-admin">`.
4. The browser loads the scripts (below); `core/start.js` calls the page's loader, which fetches its data
   from the JSON API and draws it.

## Browser code

All scripts load on every page, in a fixed order, and share one global scope: one cached set, no build step,
and a function from an earlier file can be used directly.

```
presentation/static/js/core/    shared by every page
  early.js          side-menu state before the page is drawn
  helpers.js        $, $o, esc, toast, api(), dates, confirm pop-up, pager, PAGE / showTab / openDevice
  menu.js           menu button (minimise on a computer, drawer on a phone), RADIUS drop-down, account menu
  account.js        signed-in user (ME), sign out, change own password
  backup-jobs.js    start / follow / stop a backup (top-bar chip on every page)
  search.js         global search (Ctrl+K)
  start.js          PAGE_INIT: runs the open page's loader; idle sign-out
  responsive.js     tables become cards on phones
presentation/static/js/pages/   one file per screen (dashboard, devices, backups, reports, jobs, logs, users, settings, radius)
presentation/static/js/pages/auth.js   sign-in page only
```

Rules that keep this safe:

- **Only the open screen loads data.** `PAGE` (from `body[data-page]`) selects the loader in `PAGE_INIT`.
- **Page bindings never break other pages.** A page script binds its buttons with `$o("#id")`, which returns a
  detached placeholder when the element is not on this page. Code that runs on a timer checks `PAGE`.
- **Live updates in place.** `morph(el, html)` changes only what differs, so tables and charts do not flicker.
- **Navigation is plain links.** `showTab("devices")` and `openDevice(id)` change `location`; links saved from the
  old one-page version (`/#devices`, `/#device/12`) are redirected by `start.js`.

Styles: `presentation/static/css/app.css` for the application (sections: tokens, base, shell, components, pages, motion,
responsive) and `presentation/static/css/auth.css` for the sign-in page.

## Backups

`business/backups/jobs.py` runs one job at a time: ping every device in parallel, then up to N SSH sessions
(Settings → Performance). For each device `business/backups/services.py`:

1. reads the configuration over SSH (`engine.py`, vendor command from `data_access/devices/vendors.py`)
2. compares it with the latest saved version, ignoring lines that change on every read (clock, timestamps)
3. unchanged → records the check only; changed → writes a hidden `.part` file, then renames it **inside the same
   database transaction** that records the result (`data_access/backups/repositories.py`), then writes a SHA-256 checksum

A failure or Stop at any point leaves no partial file and does not change the last good backup.

Slow devices, login bursts and offline devices are handled as described in
[BACKUP_RELIABILITY.md](BACKUP_RELIABILITY.md): VAULT waits while a device sends data and gives up only when it
goes silent; logins are paced; temporary failures get an automatic second try in the same job; offline and
still-failing devices wait in a retry queue. A device's failure is written to the database only when final.

## RADIUS / AAA

The panel writes the standard FreeRADIUS tables (`radcheck`, `radusergroup`, `radgroupreply`, `nas`) and one
extra table, `dbms_user_nas` (where a user may log in). FreeRADIUS uses three policies from `deploy/radius/`:

- `dbms_dynamic_clients`: a switch added on NAS Clients works without a restart
- `dbms_device_limit`: refuses a login on a device outside the user's list
- `dbms_huawei_levels`: caps the level at 3 on "Huawei (levels 0-3 only)" switches

Access levels send each vendor's attribute with `:=`, so nothing else can override the level chosen in the
panel. `deploy/radius/check_levels.sh` verifies the whole chain on a server.

- **Passwords** are stored only as salted SHA-256 (`SSHA2-256-Password`, `services.hash_password`); FreeRADIUS
  checks them with PAP. `manage.py radius_hash_passwords` (run by the installer) converts clear-text ones left
  by older versions, keeping the same passwords.
- **BlastRADIUS** (CVE-2024-3596): `deploy/radius/enable_blastradius.sh` (run by the installer) makes sure
  radiusd.conf has `require_message_authenticator = auto` and `limit_proxy_state = auto`.
- **Firewall**: UDP 1812 / 1813 and 514 open only for NAS Clients addresses (`deploy/radius/vault-radius-firewall`,
  run after every NAS change).
- **NAS names**: an entry added without a name gets the host name the device sends in its syslog
  (`services.name_nas_from_syslog`, called by the receiver); a typed name is never changed.

## Session Log

```
 device ──syslog──> receiver.py ──parsers.py──> CommandEvent (dbms)     logins, commands, changes
                         │                       SyslogSource            per sender: counts, host name
                         └─ heartbeat ────────> ReceiverState           running, ignored / dropped counts
 FreeRADIUS ──────────────────────────────────> radpostauth / radacct   RADIUS logins and logouts
                                                        │
 selectors.sessions(): events + RADIUS logins / logouts ┘──> one card per login (login → commands → logout)
```

- A session is built on each request from the period asked for (plus 24 hours before it, for a session already
  going), at most 20,000 events; with no logout it shows as active for 5 minutes after the last event.
- Device names: NAS Clients, then Device Inventory, then the syslog host name (`selectors._namer`).
- The warnings on the page (receiver not installed or not running, messages ignored or dropped) carry the
  steps to fix them; ignored / dropped can be cleared (`POST /api/radius/commands/notes/<note>/dismiss`).
- Cisco IOS logs configuration commands only (archive log); show / ping come from the event manager applet in
  Device Setup. The part after a pipe is never sent by Cisco.
- Authentication Audit's **From** falls back to the Session Log (`selectors.fill_login_sources`) when the
  device sends no Calling-Station-Id.

## Security

- Every JSON endpoint goes through `core/api.py` (`@api(GET="viewer", POST="operator", ...)`): method and
  role are checked on the server, never only in the browser.
- Device passwords are encrypted with Fernet (`data/secret.key`); they reach the browser only when an
  administrator presses Show, which is audited.
- Strict Content-Security-Policy (no inline or eval scripts), HSTS on HTTPS, no search-engine indexing,
  generic error messages (`core/middleware.py`).
- Sign-in lockout after 5 wrong passwords, idle sign-out, sign-in history with the real client IP.
