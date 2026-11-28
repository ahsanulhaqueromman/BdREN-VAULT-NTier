"""
The tiny API layer used by every JSON endpoint.

    @api(GET="viewer", POST="operator")
    def devices(request): ...

* only the listed HTTP methods are allowed (others get 405)
* the person must be signed in (401) and have at least the listed role (403)
* raise ApiError(400, "message") anywhere to answer with {"error": "message"}
* unexpected exceptions are logged and hidden from the browser (500)
"""
import logging
from functools import wraps

from django.http import Http404, JsonResponse

from core.exceptions import ApiError  # noqa: F401  (re-exported for views)

logger = logging.getLogger("dbms")


def error_response(status, message):
    return JsonResponse({"error": message}, status=status)


def api(**method_roles):
    allowed = {method.upper(): role for method, role in method_roles.items()}

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated or not user.is_active:
                return error_response(401, "Please sign in")
            if request.method not in allowed:
                response = error_response(405, "Method not allowed")
                response["Allow"] = ", ".join(allowed)
                return response
            if not user.has_role(allowed[request.method]):
                logger.warning("API access denied for user=%s path=%s method=%s",
                               getattr(user, "username", "-"), request.path, request.method)
                return error_response(403, "Your role does not allow this action")
            try:
                return view(request, *args, **kwargs)
            except ApiError as e:
                return error_response(e.status, e.message)
            except Http404:
                return error_response(404, "Not found")
            except Exception:
                logger.exception("Unhandled error on %s %s", request.method, request.path)
                return error_response(500, "Internal server error")
        return wrapper
    return decorator
