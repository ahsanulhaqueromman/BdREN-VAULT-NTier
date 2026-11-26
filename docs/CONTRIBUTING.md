# Contributing

How to make the common changes without breaking anything. Background: [ARCHITECTURE.md](ARCHITECTURE.md).

## Run it on your computer

VAULT needs MySQL 8 / MariaDB 10.6+. Create a database as in the README
("Database"), put `DBMS_DB_*` in `.env`, then:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
python manage.py migrate
python manage.py createsuperuser
python manage.py serve --port 8000
```

Open http://127.0.0.1:8000. RADIUS pages need a FreeRADIUS MySQL database (`RADIUS_DB_*` in `.env`); without
one they show "RADIUS database is not reachable", and everything else works.

## Add a page

1. **Registry**: add a `Page(...)` to `PAGES` in `core/pages.py` (key, URL path, title, menu group,
   template, icon, role). The URL, menu item, breadcrumb and access check come from this one line.
2. **Template**: create it, for example `presentation/templates/inventory/racks.html`:

   ```django
   {% extends "base.html" %}
   {# Racks (/racks): what this page shows. Data: pages/racks.js #}
   {% block content %}
   <section id="racks">
     <div class="title"><div>{% include "components/_page_heading.html" with title=page.title subtitle="One sentence on what this page is for." %}</div></div>
     <div id="rackList"></div>
   </section>
   {% endblock %}
   ```
3. **Icon**: `presentation/templates/components/icons/<icon>.svg` (18 × 18, `stroke="currentColor"`).
4. **Script**: `presentation/static/js/pages/racks.js` with a loader `async function loadRacks(){...}`. Bind buttons with
   `$o("#id")` so the file is harmless on other pages. Add the `<script>` to `presentation/templates/base.html` before
   `core/search.js`, and `racks:loadRacks` to `PAGE_INIT` in `presentation/static/js/core/start.js`.
5. **API**: reads in `data_access/<app>/selectors.py`, changes in `business/<app>/services.py`, and the
   endpoint in `presentation/<app>/views.py` with `@api(GET="viewer", ...)` plus its `urls.py` (see "Add a JSON endpoint").

## Where does my code go?

| You are writing... | Put it in | Never in |
|---|---|---|
| reading the request, the answer, the audit entry | `presentation/<app>/views.py` | |
| a rule, a validation, anything that changes data | `business/<app>/services.py` | `views.py` |
| a database query that only reads | `data_access/<app>/selectors.py` | `views.py`, `services.py` |
| talking to a device, files, the OS, FreeRADIUS | `data_access/<app>/` (`ssh_client.py`, `repositories.py` ...) | `views.py` |
| a table or a column | `database/<app>/models.py` | anywhere else |

`python manage.py check_architecture` tells you at once when something is in the wrong place.

## Add a JSON endpoint

```python
# data_access/inventory/selectors.py  - reads (tier 3)
def racks():
    return [{"id": r.id, "name": r.name} for r in Rack.objects.order_by("name")]

# business/inventory/services.py      - rules and changes (tier 2)
def create_rack(name):
    if not name:
        raise ApiError(400, "Enter a name for the rack.")      # shown to the user as a clear message
    return Rack.objects.create(name=name)

# presentation/inventory/views.py     - HTTP only (tier 1)
@api(GET="viewer", POST="operator")          # method -> lowest role allowed
def racks(request):
    if request.method == "GET":
        return JsonResponse({"racks": selectors.racks()})
    rack = services.create_rack((parse_json(request).get("name") or "").strip())
    record_audit(request, "rack.create", rack.name)
    return JsonResponse({"id": rack.id}, status=201)
```

Error messages are shown to users as notifications: write them as a full sentence that says what to do.

## Add a device vendor

One entry in `VENDORS` in `data_access/devices/vendor_registry.py` (login driver and backup command). Optional: a logo in
`presentation/static/img/vendors/` and its name in `VENDOR_LOGO` in `presentation/static/js/pages/devices.js`.

## Notifications and texts

- `toast("The device was added.", {title:"Device added"})`: success. Types: `success`, `info`, `warning`,
  `error`. Errors stay until closed. Add `action:{label:"Open", run:()=>showTab("logs")}` for a next step.
- `confirmAction({...})` before anything destructive; `errorState(what, err)` when a section cannot load.
- Write titles in Title Case ("Device added"), messages as sentences that say what happened and what to do.
  Never show stack traces, paths or database errors: log them on the server instead.

## Before you ship

- `python manage.py check_architecture`, `python manage.py check --deploy` and `python -m pyflakes presentation business data_access database core config`
  must be clean.
- Open every page in the browser (desktop and phone width) with an Administrator and a Viewer account; the
  browser console must show no errors.
- Raise the `?v=` numbers in `presentation/templates/base.html` if CSS or JS changed.
- Write a clear commit message: the Git log is the change history.
- Build the release zip with `python deploy/build/build_release.py` (it leaves out `.env`, the runtime `data/` and
  `logs/` folders, caches and tests, and stops if any template, static file or module is missing).
  Do not zip by hand: excluding a folder name such as `logs` by hand also drops `presentation/templates/logs/`.
  Deploy it with [DEPLOY.md](DEPLOY.md).
