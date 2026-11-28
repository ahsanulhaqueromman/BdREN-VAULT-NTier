"""Encryption of device passwords (MultiFernet, key in data/secret.key with optional rotation)."""
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

from core.keys import load_or_create_key


@lru_cache(maxsize=1)
def _fernet():
    raw = load_or_create_key(settings.FERNET_KEY_FILE, Fernet.generate_key)
    keys = [Fernet(line.strip()) for line in raw.splitlines() if line.strip()]
    old_file = settings.FERNET_KEY_FILE.with_name(settings.FERNET_KEY_FILE.name + ".old")
    if old_file.is_file() and not old_file.is_symlink():
        for line in old_file.read_bytes().splitlines():
            if line.strip():
                keys.append(Fernet(line.strip()))
    return MultiFernet(keys)


def encrypt(value):
    """Plain text -> encrypted text ('' stays '')."""
    if not value:
        return ""
    if not isinstance(value, str):
        raise TypeError("Value to encrypt must be a string")
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token):
    """Encrypted text -> plain text ('' stays '')."""
    if not token:
        return ""
    if not isinstance(token, str):
        raise TypeError("Token to decrypt must be a string")
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Encrypted credential could not be verified") from exc


def rotate_token(token):
    """Re-encrypt an existing token under the newest primary key."""
    return _fernet().rotate(token.encode()).decode() if token else ""
