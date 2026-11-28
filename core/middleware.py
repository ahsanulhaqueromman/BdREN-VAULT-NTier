"""Security headers for every response.

This is a private operations panel: nothing may be indexed by search engines, embedded in other sites,
cached by browsers / proxies, or opened by another origin. See also robots.txt (core/views.py) and the
`ident=""` waitress option in core/management/commands/serve.py (no "Server: waitress" header).
"""
import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
       "connect-src 'self'; font-src 'self'; manifest-src 'self'; worker-src 'none'")

PERMISSIONS = ("camera=(), microphone=(), geolocation=(), payment=(), usb=(), serial=(), bluetooth=(), "
               "hid=(), midi=(), magnetometer=(), gyroscope=(), accelerometer=(), display-capture=(), "
               "browsing-topics=()")


class ActiveUserMiddleware:
    """Fail-closed session guard: immediately revoke sessions for disabled users or expired absolute lifetimes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            if not user.is_active:
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse({"error": "Account is disabled"}, status=401)
                return redirect(settings.LOGIN_URL)
            max_age = getattr(settings, "SESSION_ABSOLUTE_MAX_SECONDS", 24 * 60 * 60)
            now = int(time.time())
            created_at = request.session.get("_created_at")
            if created_at is None:
                request.session["_created_at"] = now
            elif max_age and (now - int(created_at)) > max_age:
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse({"error": "Session expired. Please sign in again."}, status=401)
                return redirect(f"{settings.LOGIN_URL}?reason=idle")
        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        h = response.headers
        h["X-Permitted-Cross-Domain-Policies"] = "none"
        h["Permissions-Policy"] = PERMISSIONS
        h["Content-Security-Policy"] = CSP
        h["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet, noimageindex"   # never in search results
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["Cache-Control"] = "no-store, no-cache, must-revalidate, private"     # static files are served earlier by WhiteNoise
        h["Pragma"] = "no-cache"
        h.pop("Server", None)
        return response
