"""Settings package. DJANGO_SETTINGS_MODULE stays "config.settings".

    base.py          every setting, read from environment variables / .env (used by both)
    production.py    the default: a server installed with deploy/install.sh
    development.py   a developer's computer: set DJANGO_ENV=development
"""
import os

from .base import *  # noqa: F401,F403

if os.environ.get("DJANGO_ENV", "production").strip().lower() == "development":
    from .development import *  # noqa: F401,F403
else:
    from .production import *  # noqa: F401,F403
