"""Secret key files. Pure Python on purpose: settings.py imports this before Django is configured."""
import os
import stat
import tempfile
from pathlib import Path


def _strip_controls_and_validate(data, path):
    if not data:
        raise ValueError(f"Key file {path} is empty")
    return data


def load_or_create_key(path, make):
    """Read a secret from disk, creating it atomically with owner-only permissions on first start."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"Refusing to follow symlink for key file: {path}")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        key_bytes = make()
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            os.chmod(tmp_name, 0o600)
        except OSError:
            pass
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(key_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            if not path.exists():
                os.replace(tmp_name, path)
            else:
                os.unlink(tmp_name)
        except Exception:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            raise
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    elif os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    return _strip_controls_and_validate(path.read_bytes(), path)
