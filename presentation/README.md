# Tier 1 - Presentation

What the user sees and touches: pages, the JSON API, the browser code and the look.

**Rule:** this tier talks only to `application/`. It never reads or writes the database itself
(no `Model.objects`, no `persistence.*.models` imports). `python manage.py check_architecture` enforces this.

```
Browser ──HTTPS──> nginx ──> config/urls.py ──> presentation/<area>/urls.py ──> views.py
                                                                                   │ calls
                                                                                   ▼
                                                                   application/<area>/services.py / selectors.py
```

## Folders

| Folder | Files | Job |
|---|---|---|
| `core/` | `pages.py` | The page registry: every screen, its URL, menu group, template, icon and role |
| | `views.py` | Renders a page (base.html + the page's template), `/healthz`, `/robots.txt`, CSRF failure page |
| | `api.py` | `@api(GET="viewer", POST="operator")`: method and role check for every JSON endpoint |
| | `middleware.py` | Security headers (CSP, HSTS ...) on every response |
| `accounts/` | `urls.py`, `views.py` | `/login`, `/logout`, `/setup`, `/api/me`, `/api/users` |
| `devices/` | `urls.py`, `views.py` | `/api/devices` (+ import, export, delete), `/api/credentials` |
| `backups/` | `urls.py`, `views.py` | `/api/backup`, `/api/jobs`, `/api/logs`, `/api/backups`, `/api/diff`, `/api/reports`, `/api/audit`, `/api/notifications` |
| `monitoring/` | `urls.py`, `views.py` | `/api/ping`, `/api/dashboard` |
| `scheduling/` | `urls.py`, `views.py` | `/api/settings` |
| `radius/` | `urls.py`, `views.py` | `/api/radius/users`, `/api/radius/nas`, `/api/radius/audit` |
| `commandlog/` | `urls.py`, `views.py` | `/api/radius/commands` (Session Log) |
| `templates/` | `base.html`, `components/`, one folder per screen | HTML of every page |
| `static/` | `css/`, `js/core/`, `js/pages/`, `img/` | Styles, browser code, logos |

## Adding a screen

1. Add it to `core/pages.py` (key, URL, template, role).
2. Create `templates/<area>/<page>.html` that extends `base.html`.
3. Create `static/js/pages/<page>.js` with a loader and register it in `PAGE_INIT` (`static/js/core/start.js`).
4. Add the JSON endpoint in `<area>/views.py` + `<area>/urls.py`; let it call a selector or service.
5. After changing CSS or JS, raise the `?v=` numbers in `templates/base.html`.
