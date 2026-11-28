"""Production settings (the default).

Enforces production-grade defaults on top of base.py while keeping server-specific values in .env.
"""
from .base import ALLOWED_HOSTS, MIDDLEWARE

DEBUG = False

# Mitigate BREACH compression side-channel attacks on HTTPS responses containing CSRF tokens or secrets.
MIDDLEWARE = [m for m in MIDDLEWARE if m != "django.middleware.gzip.GZipMiddleware"]

# Prevent hung SMTP servers from stalling connections or alert threads.
EMAIL_TIMEOUT = 5

if "*" in ALLOWED_HOSTS:
    raise ValueError("Wildcard '*' in DJANGO_ALLOWED_HOSTS is forbidden in production.")
