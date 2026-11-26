from django.core.management.base import BaseCommand
from django.db import connections, models

from apps.radius.models import AuditLog, NasRole, UserDevice, UserGrant
from apps.radius.repositories.db_router import DB
from apps.radius.services.radius_service import convert_legacy_limits, normalize_roles, seed_groups


class Command(BaseCommand):
    help = ("Prepare an existing FreeRADIUS database for the RADIUS Admin pages: create the panel's "
            "tables when they are missing (audit log, per-switch login limits, device types), convert "
            "old per-switch limits and seed the access-level groups. Safe to run again.")

    def handle(self, *args, **opts):
        connection = connections[DB]
        existing = connection.introspection.table_names()
        for model in (AuditLog, UserDevice, NasRole, UserGrant):
            table = model._meta.db_table
            if table in existing:
                self.stdout.write(f"{table}: already there.")
            else:
                with connection.schema_editor() as editor:
                    editor.create_model(model)
                self.stdout.write(self.style.SUCCESS(f"{table}: created."))
        self.widen_role_column(connection)
        self.widen_postauth_pass(connection, existing)
        self.index_login_time(connection, existing)
        fixed = normalize_roles()
        if fixed:
            self.stdout.write(self.style.SUCCESS(f"Device types: {fixed} row(s) set to one spelling."))
        converted = convert_legacy_limits()
        if converted:
            self.stdout.write(self.style.SUCCESS(
                "Per-switch limits moved out of radcheck for: " + ", ".join(sorted(set(converted)))))
        seed_groups()
        self.stdout.write(self.style.SUCCESS("Access-level groups seeded."))

    def index_login_time(self, connection, existing):
        """radpostauth (written by FreeRADIUS) has no index on authdate; the Authentication Audit summary
        counts the logins of the last 24 hours / 7 / 30 days, which would read the whole table without it."""
        if "radpostauth" not in existing:
            return
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "radpostauth")
            if any(c.get("index") and (c.get("columns") or [None])[0] == "authdate" for c in constraints.values()):
                return
            cursor.execute("CREATE INDEX dbms_authdate ON radpostauth (authdate)")
        self.stdout.write(self.style.SUCCESS("radpostauth: added an index on authdate."))

    def widen_postauth_pass(self, connection, existing):
        """radpostauth (written by FreeRADIUS, not a VAULT table) logs the password/credential the device sent
        with each login attempt. The standard FreeRADIUS schema makes that column only 64 characters wide; a
        device that sends a longer credential (a long CHAP response, for example) then fails the INSERT with
        "Data too long for column 'pass'" - and on some setups that error stops FreeRADIUS answering the
        request at all, so the device sees no reply, marks RADIUS down, and every login fails until it
        retries. Only MySQL/MariaDB enforces the column width (SQLite does not), and only there is this safe."""
        if "radpostauth" not in existing or connection.vendor != "mysql":
            return
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, "radpostauth")
            size = next((c.internal_size for c in columns if c.name == "pass"), None)
            if size is None or size >= 253:
                return
            cursor.execute("ALTER TABLE radpostauth MODIFY pass VARCHAR(253) NOT NULL DEFAULT ''")
        self.stdout.write(self.style.SUCCESS(f"radpostauth.pass: widened from {size} to 253."))

    def widen_role_column(self, connection):
        """dbms_nas_role.role was created 30 characters wide by the first build that had it; it is 50 now."""
        field = NasRole._meta.get_field("role")
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, NasRole._meta.db_table)
        size = next((c.internal_size for c in columns if c.name == "role"), None)
        if size and size < field.max_length:
            old = models.CharField(max_length=size, default="Other")
            old.set_attributes_from_name("role")
            old.model = NasRole
            with connection.schema_editor() as editor:
                editor.alter_field(NasRole, old, field)
            self.stdout.write(self.style.SUCCESS(f"dbms_nas_role.role: widened from {size} to {field.max_length}."))
