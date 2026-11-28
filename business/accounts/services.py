"""Accounts - business layer: sign-in checks, lockout, password rules and every change to web users."""
import re
import threading

from django.contrib.auth.hashers import check_password as check_hash
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import ApiError

from data_access.accounts import selectors
from database.accounts.models import ROLE_LEVEL, Role, User

MAX_FAILS, LOCK_SECONDS = 5, 300
_DUMMY_HASH = make_password("not-a-real-password")      # keeps timing equal for unknown usernames
MAX_FAILS_PER_IP = 20          # wrong passwords from ONE address across all usernames (password spraying)
MAX_FAILS_PER_ACCOUNT = 15     # global wrong passwords for ONE username across all IPs (distributed brute force)
_LOCK_MUTEX = threading.Lock()


def _revoke_user_sessions(user_id):
    """Delete all active Django sessions belonging to `user_id`."""
    uid = str(user_id)
    to_delete = []
    for s in Session.objects.filter(expire_date__gt=timezone.now()).iterator(chunk_size=500):
        try:
            if str(s.get_decoded().get("_auth_user_id")) == uid:
                to_delete.append(s.session_key)
        except Exception:
            continue
    if to_delete:
        Session.objects.filter(session_key__in=to_delete).delete()


def check_username(username):
    """Error text for an invalid username, or '' when it is fine."""
    if not isinstance(username, str):
        return "Username must be text"
    ok = re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username or "")
    return "" if ok else "Username must be 3-32 characters: letters, numbers, dot, dash or underscore"


def check_password(password, user=None):
    """Error text for a weak password, or '' when it is fine.

    Rules (config/settings.py AUTH_PASSWORD_VALIDATORS): at least 12 characters, not whitespace-only,
    not a commonly used password, not all digits, not similar to the username. Maximum 128 characters.
    """
    if not isinstance(password, str):
        return "Password must be text"
    if not password or not password.strip():
        return "Password cannot be empty or whitespace"
    if len(password) > 128:
        return "Password is too long"
    try:
        validate_password(password, user=user)
    except ValidationError as e:
        return " ".join(e.messages)
    return ""


def create_user(username, password, role):
    """Create a user; raises ApiError(409) when the name is taken (ignoring case)."""
    if User.objects.filter(username__iexact=username).exists():
        raise ApiError(409, "That username already exists")
    try:
        return User.objects.create_user(username=username, password=password, role=role)
    except IntegrityError:
        raise ApiError(409, "That username already exists")


def check_credentials(username, password):
    """(user, password_ok) for a sign-in attempt. Unknown users take as long as known ones (no username probing)."""
    user = selectors.find_user(username)
    if not isinstance(password, str) or len(password) > 128:
        check_hash("x", _DUMMY_HASH)
        return user, False
    ok = check_hash(password, user.password if user else _DUMMY_HASH) and user is not None
    return user, ok


def create_validated_user(username, password, role):
    """Add a web user after checking the name, password strength and role."""
    if not isinstance(role, str) or role not in ROLE_LEVEL:
        raise ApiError(400, "Invalid role")
    error = check_username(username) or check_password(password, user=User(username=username))
    if error:
        raise ApiError(400, error)
    return create_user(username, password, role)


def change_own_password(user, current, new):
    """Change the signed-in user's password (the view then keeps this session and drops the others)."""
    if not isinstance(current, str) or not isinstance(new, str):
        raise ApiError(400, "Enter the current and the new password")
    pw_lock_key = f"pw-change-locked:{user.pk}"
    if cache.get(pw_lock_key) is not None:
        raise ApiError(429, "Too many incorrect current password attempts. Try again later.")
    if len(current) > 128 or not user.check_password(current):
        fail_key = f"pw-change-fail:{user.pk}"
        with _LOCK_MUTEX:
            count = cache.get(fail_key, 0) + 1
            if count >= MAX_FAILS:
                cache.set(pw_lock_key, 1, LOCK_SECONDS)
                cache.delete(fail_key)
            else:
                cache.set(fail_key, count, LOCK_SECONDS)
        raise ApiError(400, "Current password is incorrect")
    cache.delete_many([f"pw-change-fail:{user.pk}", pw_lock_key])
    if current == new:
        raise ApiError(400, "New password must be different from your current password")
    error = check_password(new, user)
    if error:
        raise ApiError(400, error)
    user.set_password(new)
    user.save()


def update_user(target, acting_user, data):
    """Change role / active flag / password. You cannot demote yourself or remove the last administrator."""
    role = data.get("role", target.role)
    active = data.get("active", target.is_active)
    if not isinstance(role, str) or role not in ROLE_LEVEL:
        raise ApiError(400, "Invalid role")
    if not isinstance(active, bool):
        raise ApiError(400, "active must be a boolean")
    if target.is_superuser and not acting_user.is_superuser:
        raise ApiError(403, "Only a superuser can modify a superuser account")
    if target.is_superuser and role != Role.ADMIN:
        raise ApiError(400, "A superuser account must keep the Administrator role")
    if target.pk == acting_user.pk and (role != target.role or not active):
        raise ApiError(400, "You cannot change your own role or disable your own account")
    first_id = selectors.first_user_id()
    if target.pk == first_id and (role != target.role or not active):
        raise ApiError(400, "The first account cannot be demoted or disabled")
    password = data.get("password")
    if password not in (None, ""):
        if target.pk == acting_user.pk:
            raise ApiError(400, "Use Change Password in your account menu to change your own password")
        if target.pk == first_id and not acting_user.is_superuser:
            raise ApiError(403, "Only a superuser can reset the first account's password")
        err = check_password(password, user=target)
        if err:
            raise ApiError(400, err)
    with transaction.atomic():
        locked_target = User.objects.select_for_update().get(pk=target.pk)
        if locked_target.role == Role.ADMIN and locked_target.is_active and (role != Role.ADMIN or not active) \
                and User.objects.filter(role=Role.ADMIN, is_active=True).exclude(pk=locked_target.pk).count() == 0:
            raise ApiError(400, "At least one active administrator is required")
        locked_target.role, locked_target.is_active = role, active
        if password not in (None, ""):
            locked_target.set_password(password)
        locked_target.save()
        target.role, target.is_active = locked_target.role, locked_target.is_active
    if not active or password not in (None, ""):
        _revoke_user_sessions(target.pk)


def delete_user(target, acting_user):
    if target.pk == acting_user.pk:
        raise ApiError(400, "You cannot delete your own account")
    if target.is_superuser and not acting_user.is_superuser:
        raise ApiError(403, "Only a superuser can delete a superuser account")
    if target.pk == selectors.first_user_id():
        raise ApiError(400, "The first account cannot be deleted")
    with transaction.atomic():
        locked_target = User.objects.select_for_update().get(pk=target.pk)
        if locked_target.role == Role.ADMIN and locked_target.is_active \
                and User.objects.filter(role=Role.ADMIN, is_active=True).exclude(pk=locked_target.pk).count() == 0:
            raise ApiError(400, "At least one active administrator is required")
        pk = locked_target.pk
        locked_target.delete()
    _revoke_user_sessions(pk)


# ---------- login lockout: 5 wrong passwords lock that client + username for 5 minutes ----------
def _clean_name(username):
    return re.sub(r"[^a-z0-9._@-]", "_", (username or "").lower())[:64]


def _lock_key(ip, username):
    # the name comes straight from the sign-in form: keep the cache key short and free of odd characters
    return f"login-fail:{ip}:{_clean_name(username)}"


def is_locked(ip, username):
    name = _clean_name(username)
    return (cache.get(_lock_key(ip, username) + ":locked") is not None
            or cache.get(f"login-ip-locked:{ip}") is not None
            or (bool(name) and cache.get(f"login-acct-locked:{name}") is not None))


def _bump_counter(fail_key, lock_key, threshold):
    if cache.add(fail_key, 1, LOCK_SECONDS):
        count = 1
    else:
        try:
            count = cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, LOCK_SECONDS)
            count = 1
    if count >= threshold:
        cache.set(lock_key, 1, LOCK_SECONDS)
        cache.delete(fail_key)


def register_failure(ip, username):
    with _LOCK_MUTEX:
        _bump_counter(f"login-ip-fail:{ip}", f"login-ip-locked:{ip}", MAX_FAILS_PER_IP)
        key = _lock_key(ip, username)
        _bump_counter(key, key + ":locked", MAX_FAILS)
        name = _clean_name(username)
        if name:
            _bump_counter(f"login-acct-fail:{name}", f"login-acct-locked:{name}", MAX_FAILS_PER_ACCOUNT)


def clear_failures(ip, username):
    name = _clean_name(username)
    keys = [_lock_key(ip, username), _lock_key(ip, username) + ":locked"]
    if name:
        keys += [f"login-acct-fail:{name}", f"login-acct-locked:{name}"]
    cache.delete_many(keys)
