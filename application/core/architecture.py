"""The N-tier rules of this project, checked automatically.

The code is split into three tiers, one top-level folder each. A tier may only use the tier below it:

    presentation/   Tier 1  views.py, urls.py, api(), middleware, pages, templates/, static/
                            reads the request, calls the application tier, answers in HTML or JSON
    application/    Tier 2  services.py (rules and every change), selectors.py (every read),
                            integrations: engine.py (SSH), storage.py (files), jobs.py, parsers.py, receiver.py ...
    persistence/    Tier 3  models.py, migrations/, router.py (radius database), crypto.py (encrypted fields)

Inside a tier every area (accounts, devices, backups, ...) has its own folder. Between areas only the public
modules of another area may be used (PUBLIC below); `core` is shared by every area. Inside the application
tier, selectors.py never imports services.py (reads do not change data). Maintenance commands
(application/management/commands/) and migrations may use any model directly.
Run:  python manage.py check_architecture
"""
import ast
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

TIERS = {"presentation": 1, "application": 2, "persistence": 3}
# modules of another area that may be imported (its public face)
PUBLIC = {"selectors", "services", "audit", "vendors", "jobs", "engine", "pages", "api", "utils", "crypto",
          "netguard", "keys", "alerts", "background", "router", "errors", "period", "summary_report"}
FORBIDDEN_SAME_AREA = {
    # module     : modules of the SAME area it must not import
    "selectors": {"services"},
}


@dataclass
class Violation:
    path: str
    line: int
    rule: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.rule}"


def _imports(tree):
    """(line, dotted module, imported names) for every absolute import in a module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                yield node.lineno, None, []
            else:
                yield node.lineno, node.module or "", [a.name for a in node.names]
        elif isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name, []


def _target(base, names):
    """[(tier, area, module)] an import points to, for imports of the three tiers; else []."""
    parts = base.split(".")
    if parts[0] not in TIERS or len(parts) < 2:
        return []
    if len(parts) == 2:                               # "from application.devices import selectors"
        return [(parts[0], parts[1], n) for n in names]
    return [(parts[0], parts[1], parts[2])]


def check(root=None):
    """Return every Violation found in the three tiers (empty list = the architecture is respected)."""
    root = Path(root or settings.BASE_DIR)
    found = []
    for tier in TIERS:
        for path in sorted((root / tier).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            parts = path.relative_to(root / tier).parts
            if len(parts) < 2 or "migrations" in parts or parts[-1] == "tests.py":
                continue
            area, module = parts[0], path.stem
            command = area == "management"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if tier == "presentation":
                for i, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    code = text.split("#", 1)[0]
                    if ".objects." in code or "transaction.atomic" in code or "connection.cursor" in code:
                        found.append(Violation(rel, i, "presentation must not query the database: "
                                                       "use a selector or service of the application tier"))
            for line, base, names in _imports(tree):
                if base is None:
                    found.append(Violation(rel, line, "use absolute imports (tier.area.module)"))
                    continue
                for t_tier, t_area, t_mod in _target(base, names):
                    if TIERS[t_tier] < TIERS[tier]:
                        found.append(Violation(rel, line, f"{tier} must not import {t_tier} (tiers point downwards only)"))
                    if command:
                        continue
                    if tier == "presentation" and t_tier == "persistence" and t_mod == "models":
                        found.append(Violation(rel, line, f"presentation must not import models ({t_area}.models)"))
                    if t_tier == tier and t_area == area and t_mod in FORBIDDEN_SAME_AREA.get(module, ()):
                        found.append(Violation(rel, line, f"{module} must not import {t_mod} (reads do not change data)"))
                    if t_area not in (area, "core") and t_mod not in PUBLIC and t_mod != "models":
                        found.append(Violation(rel, line, f"use the public modules of {t_area}, not {t_area}.{t_mod}"))
                    if t_area not in (area, "core") and t_mod == "models" and module not in ("models", "admin"):
                        found.append(Violation(rel, line, f"read {t_area} data through application.{t_area}.selectors, "
                                                          f"not {t_area}.models"))
    return found
