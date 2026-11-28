"""Verify saved configuration snapshots against their SHA-256 sidecar files (read-only)."""
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Read-only integrity check for saved .txt backups and their .sha256 sidecars."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Check at most N newest files; 0 checks all.")

    def handle(self, *args, **opts):
        root = Path(settings.BACKUP_DIR).resolve()
        files = []
        if root.exists():
            for p in root.rglob("*.txt"):
                try:
                    if p.is_file() and not p.is_symlink() and root in p.resolve().parents:
                        files.append((p.stat().st_mtime, p))
                except OSError:
                    continue
            files.sort(key=lambda x: x[0], reverse=True)
        files = [p for _, p in files]
        limit = opts["limit"]
        if limit > 0:
            files = files[:limit]
        ok = missing = mismatch = 0
        for path in files:
            sidecar = path.with_suffix(path.suffix + ".sha256")
            if not sidecar.is_file() or sidecar.is_symlink() or root not in sidecar.resolve().parents:
                missing += 1
                self.stdout.write(self.style.WARNING(f"MISSING CHECKSUM: {path.relative_to(root)}"))
                continue
            try:
                expected = sidecar.read_text(encoding="ascii").split()[0].lower()
                actual = _sha256_file(path)
            except (OSError, ValueError, IndexError) as exc:
                mismatch += 1
                self.stdout.write(self.style.ERROR(f"READ ERROR: {path.relative_to(root)} ({exc})"))
                continue
            if expected == actual:
                ok += 1
            else:
                mismatch += 1
                self.stdout.write(self.style.ERROR(f"CHECKSUM MISMATCH: {path.relative_to(root)}"))
        self.stdout.write(f"Checked={len(files)} OK={ok} MissingChecksum={missing} MismatchOrReadError={mismatch}")
        if missing:
            self.stdout.write(self.style.WARNING("Existing snapshots from before checksum support may have no sidecar; this command does not alter files."))
        if mismatch:
            raise CommandError(f"{mismatch} backup file(s) failed SHA-256 verification")
