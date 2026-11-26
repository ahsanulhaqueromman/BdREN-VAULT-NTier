from django.db import migrations


def forwards(apps, schema_editor):
    """Settings > "Keep logs and backup files for" now offers Forever, 12, 24 or 48 months. A server that had
    1, 3 or 6 months gets 12, the shortest choice left (it keeps more, never less)."""
    AppSetting = apps.get_model("scheduling", "AppSetting")
    AppSetting.objects.filter(key="log_retention_months", value__in=("1", "3", "6")).update(value="12")


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
