"""Production settings (the default).

Everything a server needs is already in base.py and comes from .env (written by deploy/install.sh):
DJANGO_ALLOWED_HOSTS, DBMS_SECURE_COOKIES, DBMS_FORCE_HTTPS, the database passwords ... Keep server-specific
values in .env, not here, so one code base runs on every server.
"""
