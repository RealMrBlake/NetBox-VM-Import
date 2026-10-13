import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_vmware_importer", "0003_add_proxmox_endpoint_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="vcenterendpoint",
            name="request_timeout_seconds",
            field=models.PositiveIntegerField(
                default=120,
                help_text="HTTP/API read timeout in seconds.",
                validators=[
                    django.core.validators.MinValueValidator(5),
                    django.core.validators.MaxValueValidator(600),
                ],
            ),
        ),
    ]
