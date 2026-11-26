"""The architecture rules of this project, checked automatically.

Every app (apps/<app>/) has one file per layer. A file may only use the layers below it:

    PRESENTATION   views.py, urls.py        receive the request, call a service / selector, send the response
                   serializers.py           turn objects into JSON (passwords never leave the server)
    BUSINESS       services.py              rules and every change (validation, writes, transactions)
                   jobs.py, receiver.py,    background work and extra business files of an app
                   reports.py, audit.py
    DATA ACCESS    selectors.py             every database read; never changes anything
                   repositories.py          stores that are not ordinary tables: backup files on disk,
                                            the second (radius) database
                   engine.py, parsers.py    the outside world: SSH to devices, vendor syslog formats
    DATABASE       models.py                tables and fields only

Between apps only the public files of another app may be used (PUBLIC below), never its views or models.
core/ is the shared kernel every app may use. Maintenance commands (core/management/commands/), admin.py and
migrations may use any model directly.  Run:  python manage.py check_architecture
"""
import ast
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

PRESENTATION = {"views", "urls", "serializers"}
# file of an app : files of the SAME app it must not import
FORBIDDEN = {
    "models": PRESENTATION | {"services", "selectors", "repositories", "jobs", "receiver", "reports", "audit",
                              "engine", "parsers"},
    "selectors": PRESENTATION | {"services"},
    "repositories": PRESENTATION | {"services", "jobs"},
    "engine": PRESENTATION | {"services", "jobs"},
    "parsers": PRESENTATION | {"services", "jobs"},
    "services": PRESENTATION,
    "jobs": PRESENTATION,
    "receiver": PRESENTATION,
    "reports": PRESENTATION,
    "audit": PRESENTATION,
    "serializers": {"views", "urls", "services"},
}
# files of another app that may be imported (its public face)
PUBLIC = {"services", "selectors", "jobs", "engine", "repositories", "audit", "reports", "vendors", "cache_keys",
          "serializers"}


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
    """[(app, file)] an import points to."""
    parts = base.split(".")
    if parts[0] != "apps" or len(parts) < 2:
        return []
    if len(parts) == 2:                               # "from apps.devices import selectors"
        return [(parts[1], n) for n in names]
    return [(parts[1], parts[2])]


def check(root=None):
    """Return every Violation found (empty list = the architecture is respected)."""
    root = Path(root or settings.BASE_DIR)
    found = []
    for path in sorted((root / "apps").rglob("*.py")) + sorted((root / "core").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if "migrations" in parts or "tests" in parts or path.name.startswith("test"):
            continue
        in_core = parts[0] == "core"
        if in_core and "management" in parts:
            continue
        app = None if in_core else (parts[1] if len(parts) > 2 else None)
        if not in_core and app is None:
            continue
        layer = "core" if in_core else path.stem
        if layer == "admin":
            continue
        text = path.read_text(encoding="utf-8")
        if layer in PRESENTATION:
            for i, line in enumerate(text.splitlines(), 1):
                code = line.split("#", 1)[0]
                if ".objects." in code or "transaction.atomic" in code or "connection.cursor" in code:
                    found.append(Violation(rel, i, f"{layer}.py must not query the database: use a selector or service"))
        for line, base, names in _imports(ast.parse(text)):
            if base is None:
                found.append(Violation(rel, line, "use absolute imports (from apps.<app> import <file>)"))
                continue
            for t_app, t_file in _targets(base, names):
                if in_core and t_file in PRESENTATION:
                    found.append(Violation(rel, line, f"core must not import an app's {t_file}.py ({t_app})"))
                if layer in PRESENTATION and t_file == "models":
                    found.append(Violation(rel, line, f"{layer}.py must not import models ({t_app}.models): "
                                                      f"use a selector"))
                if t_app == app and t_file in FORBIDDEN.get(layer, ()):
                    found.append(Violation(rel, line, f"{layer}.py must not import {t_file}.py "
                                                      f"(layers point downwards only)"))
                if not in_core and t_app != app and t_file not in PUBLIC and not (t_file == "models" and layer == "models"):
                    found.append(Violation(rel, line, f"use the public files of {t_app} (services, selectors ...), "
                                                      f"not {t_app}.{t_file}"))
    return found
