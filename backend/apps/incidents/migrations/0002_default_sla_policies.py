from django.db import migrations

DEFAULTS = [
    # priority, respond (min), resolve (min), reminder interval (min)
    ("critical", 15, 4 * 60, 30),
    ("high", 60, 8 * 60, 60),
    ("medium", 4 * 60, 24 * 60, None),
    ("low", 24 * 60, 72 * 60, None),
]


def seed(apps, schema_editor):
    SLAPolicy = apps.get_model("incidents", "SLAPolicy")
    for priority, respond, resolve, remind in DEFAULTS:
        SLAPolicy.objects.get_or_create(
            priority=priority,
            defaults={
                "response_minutes": respond,
                "resolution_minutes": resolve,
                "reminder_interval_minutes": remind,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("incidents", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
