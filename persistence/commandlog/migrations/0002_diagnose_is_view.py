from django.db import migrations

MODE_ONLY = ("diagnose", "diagnos", "diagno", "diagn", "diag")


def forwards(apps, schema_editor):
    """Entering Huawei's diagnostic view ("diagnose" on its own) was stored as a change; it changes nothing."""
    CommandEvent = apps.get_model("commandlog", "CommandEvent")
    for word in MODE_ONLY:
        CommandEvent.objects.filter(kind="change", command__iexact=word).update(kind="command")


class Migration(migrations.Migration):
    dependencies = [
        ("commandlog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
