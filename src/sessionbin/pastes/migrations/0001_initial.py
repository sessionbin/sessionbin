from django.db import migrations, models

import sessionbin.pastes.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Paste",
            fields=[
                (
                    "slug",
                    models.CharField(
                        default=sessionbin.pastes.models._make_slug,
                        max_length=10,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "delete_token_hash",
                    models.CharField(max_length=64),
                ),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                ("size_bytes", models.PositiveIntegerField()),
                ("renderer_version", models.PositiveSmallIntegerField()),
                ("adapter_version", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("deleted_at", models.DateTimeField(blank=True, default=None, null=True)),
                ("uploader_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("harness", models.CharField(blank=True, max_length=64, null=True)),
                ("session_model", models.CharField(blank=True, max_length=128, null=True)),
                ("turn_count", models.PositiveIntegerField(blank=True, null=True)),
                ("tool_call_count", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["-created_at"], name="pastes_past_created_e90ad3_idx")
                ],
            },
        ),
    ]
