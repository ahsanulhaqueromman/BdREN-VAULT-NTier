"""Development settings: used only when DJANGO_ENV=development (never on a server).

Shows Django's error pages and reloads CSS / JS on every request. The database still comes from .env.
"""

DEBUG = True
WHITENOISE_AUTOREFRESH = True
WHITENOISE_MAX_AGE = 0
