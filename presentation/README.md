# Tier 1 - Presentation

What the user sees and the `/api/` addresses. One folder per app, plus the HTML and the browser files.

| File / folder | Main job |
|---|---|
| `<app>/views.py` | Receive the request, check the role (`@api(GET="viewer")` ...), call business or data access, send the response |
| `<app>/urls.py` | The app's `/api/` addresses |
| `devices/serializers.py` | Turn a device into JSON (passwords never leave the server) |
| `templates/` | HTML pages (`base.html` is the frame of every screen) and shared components |
| `static/` | `css/`, `js/core/` (shared scripts), `js/pages/` (one file per screen), `img/` |

Rules: no database query here (no `.objects.`), no `database.*` import. Use
`data_access.<app>.selectors` to read and `business.<app>.services` to change.

## Example: an operator presses "Backup now"

1. `presentation/backups/views.py` checks the role (`@api(POST="operator")`) and calls the business tier.
2. `business/backups/backup_jobs.py` starts a background job.
3. `data_access/backups/ssh_client.py` logs in to the device over SSH and reads the configuration.
4. `business/backups/services.py` compares it with the last version: changed or unchanged.
5. `data_access/backups/repositories.py` saves the file; `database/backups/models.py` (BackupLog) records the result.
