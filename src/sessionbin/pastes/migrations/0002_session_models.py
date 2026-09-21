from django.db import migrations, models


def to_list(apps, schema_editor):
    Paste = apps.get_model("pastes", "Paste")
    for paste in Paste.objects.exclude(session_model=None).exclude(session_model=""):
        paste.session_models = [paste.session_model]
        paste.save(update_fields=["session_models"])


def to_single(apps, schema_editor):
    Paste = apps.get_model("pastes", "Paste")
    for paste in Paste.objects.exclude(session_models=[]):
        paste.session_model = paste.session_models[0]
        paste.save(update_fields=["session_model"])


class Migration(migrations.Migration):
    dependencies = [
        ("pastes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="paste",
            name="session_models",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(to_list, to_single),
        migrations.RemoveField(
            model_name="paste",
            name="session_model",
        ),
    ]
