from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("radius", "0005_usergrant"),
    ]

    operations = [
        migrations.CreateModel(
            name="IpBlock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ip", models.CharField(max_length=45, unique=True)),
                ("first_username", models.CharField(default="", max_length=64)),
                ("last_username", models.CharField(default="", max_length=64)),
                ("nasname", models.CharField(default="", max_length=128)),
                ("hits", models.IntegerField(default=1)),
                ("created_at", models.DateTimeField()),
                ("last_seen", models.DateTimeField()),
                ("blocked_until", models.DateTimeField(db_index=True)),
            ],
            options={
                "db_table": "dbms_ip_block",
            },
        ),
    ]
