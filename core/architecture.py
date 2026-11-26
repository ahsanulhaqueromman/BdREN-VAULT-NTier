"""The architecture rules of this project, checked automatically.

Every domain app (apps/<area>/) is split into the same tiers. A module may only use the tiers below it:

    api/            1. PRESENTATION   urls.py, views.py: read the request, call a service / selector, answer
    services/       2. BUSINESS       rules and every change (validation, writes, transactions)
    tasks/                            background jobs (threads started by core/background.py)
    selectors/      3. DATA ACCESS    every database read; never changes data
    repositories/                     other stores: backup files on disk, the second (radius) database
    integrations/                     the outside world: SSH to devices, the syslog receiver
    models/         4. ENTITIES       tables only

Between apps only the public parts of another app may be used (PUBLIC below), never its api/ or models/.
core/ is the shared kernel every app may use. Maintenance commands (core/management/commands/), admin.py and
migrations may use any model directly.  Run:  python manage.py check_architecture
"""
import ast
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

# the folders of an app and the folders of the SAME app they must not import
FORBIDDEN = {
    "models": {"api", "services", "selectors", "tasks", "repositories", "integrations"},
    "selectors": {"api", "services"},
    "repositories": {"api", "services", "tasks"},
    "integrations": {"api", "services", "tasks"},
    "services": {"api"},
    "tasks": {"api"},
}
# parts of another app that may be imported (its public face)
PUBLIC = {"services", "selectors", "tasks", "integrations", "repositories", "vendors", "cache_keys"}
API = "api"


@dataclass
class Violation:
    path: str
    line: int
    rule: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.rule}"


def _imports(tree):
    """(line, dotted module or None for a relative import, imported names)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node.lineno, (None if node.level else node.module or ""), [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name, []


def _targets(base, names):
    """[(app, part)] an import points to: part is the folder (api, services ...) or root module of the app."""
    parts = base.split(".")
    if parts[0] != "apps" or len(parts) < 2:
        return []
    if len(parts) == 2:                               # "from apps.devices import vendors"
        return [(parts[1], n) for n in names]
    return [(parts[1], parts[2])]


def _part(rel_parts):
    """The tier of a file inside apps/<app>/: its folder, or the module name for a file in the app root."""
    return rel_parts[1] if len(rel_parts) > 2 else Path(rel_parts[1]).stem


def check(root=None):
    """Return every Violation found (empty list = the architecture is respected)."""
    root = Path(root or settings.BASE_DIR)
    found = []
    files = sorted((root / "apps").rglob("*.py")) + sorted((root / "core").rglob("*.py"))
    for path in files:
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if "migrations" in parts or "tests" in parts or path.name.startswith("test"):
            continue
        in_core = parts[0] == "core"
        command = in_core and "management" in parts
        app = None if in_core else parts[1]
        part = "core" if in_core else (_part(parts[1:]) if len(parts) > 2 else "")
        text = path.read_text(encoding="utf-8")
        if part == API:
            for i, line in enumerate(text.splitlines(), 1):
                code = line.split("#", 1)[0]
                if ".objects." in code or "transaction.atomic" in code or "connection.cursor" in code:
                    found.append(Violation(rel, i, "api/ must not query the database: use a selector or service"))
        for line, base, names in _imports(ast.parse(text)):
            if base is None:
                found.append(Violation(rel, line, "use absolute imports (apps.<app>.<folder>.<module>)"))
                continue
            for t_app, t_part in _targets(base, names):
                if command or part == "admin":
                    continue
                if in_core and t_part == API:
                    found.append(Violation(rel, line, f"core must not import an app's api/ ({t_app}.api)"))
                if part == API and t_part == "models":
                    found.append(Violation(rel, line, f"api/ must not import models ({t_app}.models): use a selector"))
                if t_app == app and t_part in FORBIDDEN.get(part, ()):
                    found.append(Violation(rel, line, f"{part}/ must not import {t_part}/ (tiers point downwards only)"))
                if not in_core and t_app != app and t_part not in PUBLIC and not (t_part == "models" and part == "models"):
                    found.append(Violation(rel, line, f"use the public parts of {t_app} (services, selectors ...), "
                                                      f"not {t_app}.{t_part}"))
    return found
