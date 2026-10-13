import decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_vmware_importer", "0005_add_proxmox_connection_tuning"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="vcenterendpoint",
            options={
                "ordering": ("name",),
                "verbose_name": "VMware endpoint",
                "verbose_name_plural": "VMware endpoints",
            },
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="provider",
            field=models.CharField(
                choices=[
                    ("vmware", "VMware vSphere"),
                    ("proxmox", "Proxmox VE (legacy)"),
                ],
                default="vmware",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="auth_method",
            field=models.CharField(
                choices=[
                    ("password", "Username/password"),
                    ("api_token", "API token (legacy)"),
                ],
                default="password",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="host",
            field=models.CharField(help_text="vCenter or ESXi hostname or IP address", max_length=255),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="validate_ssl",
            field=models.BooleanField(default=False, help_text="Validate the VMware endpoint certificate."),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="cluster",
            field=models.ForeignKey(
                help_text="NetBox cluster into which VMware VMs will be synchronized.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vmware_import_endpoints",
                to="virtualization.cluster",
            ),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="token_name",
            field=models.CharField(
                blank=True,
                help_text="Legacy Proxmox API token ID. Kept only for deleting old endpoints.",
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="max_retries",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Legacy connection retry setting. Kept only for compatibility with older plugin versions.",
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(10),
                ],
            ),
        ),
        migrations.AlterField(
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
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="sync_lxc_containers",
            field=models.BooleanField(default=True, verbose_name="Sync legacy Proxmox LXC containers"),
        ),
    ]
