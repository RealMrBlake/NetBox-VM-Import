import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_vmware_importer", "0004_add_endpoint_api_timeout"),
    ]

    operations = [
        migrations.AddField(
            model_name="vcenterendpoint",
            name="connect_timeout_seconds",
            field=models.PositiveIntegerField(
                default=10,
                help_text="TCP/TLS connection timeout in seconds.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(120),
                ],
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="max_retries",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Retries for safe Proxmox GET requests when the endpoint returns transient errors.",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(10),
                ],
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="retry_backoff_seconds",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("0.50"),
                help_text="Exponential retry backoff base delay in seconds.",
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("0.00")),
                    django.core.validators.MaxValueValidator(decimal.Decimal("60.00")),
                ],
            ),
        ),
    ]
