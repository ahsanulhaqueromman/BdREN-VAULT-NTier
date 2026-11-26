from django.db import migrations


class Migration(migrations.Migration):
    """The FreeRADIUS IP blocking (dbms_ip_block) is removed; deploy/radius/disable_ip_block.sh drops the table
    on the server after FreeRADIUS stops reading it (the radius database is not migrated by install.sh)."""

    dependencies = [
        ("radius", "0006_ipblock"),
    ]

    operations = [
        migrations.DeleteModel(name="IpBlock"),
    ]
