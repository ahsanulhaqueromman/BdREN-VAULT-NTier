"""Store the RADIUS passwords that are still in clear text (from older versions) as salted SHA-256, keeping
the same passwords. deploy/install.sh runs it with --yes; by hand:

    sudo -u vault /opt/vault/.venv/bin/python /opt/vault/manage.py radius_hash_passwords
"""
from django.core.management.base import BaseCommand, CommandError

from business.radius.services import cleartext_users, hash_cleartext_passwords


class Command(BaseCommand):
    help = "Store clear-text RADIUS passwords as salted SHA-256 (same passwords; cannot be undone)"

    def add_arguments(self, parser):
        parser.add_argument("--user", action="append", default=[], help="only this user (repeat for more)")
        parser.add_argument("--yes", action="store_true", help="do not ask before changing")

    def handle(self, *args, **opts):
        todo = cleartext_users(opts["user"])
        if not todo:
            self.stdout.write(self.style.SUCCESS("Nothing to do: no password is stored in clear text."))
            return
        if not opts["yes"]:
            self.stdout.write(f"{len(todo)} user(s) with a clear-text password: {', '.join(todo[:20])}"
                              + (f" and {len(todo) - 20} more" if len(todo) > 20 else ""))
            self.stdout.write("They keep the same password. This cannot be undone, and these users can then log in "
                              "with PAP only (SSH / Telnet logins on network devices use PAP).")
            if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
                raise CommandError("Stopped, nothing changed.")
        done = hash_cleartext_passwords(todo)
        self.stdout.write(self.style.SUCCESS(f"{len(done)} password(s) now stored as salted SHA-256."))
