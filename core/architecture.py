"""The architecture rules of this project, checked automatically.

The code is split into four tiers (top-level folders). Inside every tier there is one folder per app.
A tier may only use the tiers BELOW it (or files of its own tier):

    1  presentation/<app>/   views.py, urls.py, serializers.py   + presentation/templates, presentation/static
                             receive the request, call business / data access, send the response
    2  business/<app>/       services.py, jobs.py, receiver.py, reports.py
                             rules and every change (validation, writes, transactions, background work)
    3  data_access/<app>/    selectors.py, repositories.py, audit.py, engine.py, parsers.py, vendors.py ...
                             every database read, stores that are not ordinary tables, the outside world (SSH, syslog)
    4  database/<app>/       models.py, migrations/, apps.py, admin.py
                             tables and fields only

core/ is the shared kernel every tier may use (it must not use presentation). Maintenance commands
(core/management/commands/), admin.py and migrations may use any model directly.
Run:  python manage.py check_architecture
"""
import ast
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

TIERS = {"presentation": 1, "business": 2, "data_access": 3, "database": 4}
DB_PATTERNS = (".objects.", "transaction.atomic", "connection.cursor")


@dataclass
class Violation:
    path: str
    line: int
    rule: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.rule}"


def _imports(tree):
    """(line, dotted module or None for a relative import)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield node.lineno, (None if node.level else node.module or "")
        elif isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name


def _files(root):
    for top in (*TIERS, "core"):
        yield from sorted((root / top).rglob("*.py"))


def check(root=None):
    """Return every Violation found (empty list = the architecture is respected)."""
    root = Path(root or settings.BASE_DIR)
    found = []
    for path in _files(root):
        parts = path.relative_to(root).parts
        rel = path.relative_to(root).as_posix()
        if "migrations" in parts or "tests" in parts or path.name.startswith("test") or path.name == "admin.py":
            continue
        if parts[0] == "core" and "management" in parts:
            continue
        tier = parts[0]
        rank = TIERS.get(tier, 0)                       # core = 0: may use every tier except presentation
        text = path.read_text(encoding="utf-8")
        if tier == "presentation":
            for i, line in enumerate(text.splitlines(), 1):
                code = line.split("#", 1)[0]
                if any(p in code for p in DB_PATTERNS):
                    found.append(Violation(rel, i, "presentation must not query the database: "
                                                   "use data_access (selectors) or business (services)"))
        for line, module in _imports(ast.parse(text)):
            if module is None:
                found.append(Violation(rel, line, "use absolute imports (from <tier>.<app> import <file>)"))
                continue
            target = module.split(".")[0]
            if target not in TIERS:
                continue
            if tier == "core":
                if target == "presentation":
                    found.append(Violation(rel, line, f"core must not import presentation ({module})"))
                continue
            if TIERS[target] < rank:
                found.append(Violation(rel, line, f"{tier} must not import {target} ({module}): "
                                                  f"tiers point downwards only"))
            if tier == "presentation" and target == "database":
                found.append(Violation(rel, line, f"presentation must not import models ({module}): "
                                                  f"use data_access (selectors)"))
    return found
