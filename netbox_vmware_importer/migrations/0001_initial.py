import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("dcim", "0001_initial"),
        ("tenancy", "0001_initial"),
        ("virtualization", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="VCenterEndpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("host", models.CharField(help_text="vCenter or ESXi hostname or IP address", max_length=255)),
                (
                    "port",
                    models.PositiveIntegerField(
                        default=443,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(65535),
                        ],
                    ),
                ),
                ("username", models.CharField(max_length=255)),
                ("password_ciphertext", models.TextField(blank=True, editable=False)),
                ("validate_ssl", models.BooleanField(default=False, help_text="Validate the VMware endpoint certificate.")),
                (
                    "include_name_regex",
                    models.CharField(
                        blank=True,
                        help_text="Only synchronize matching VM names. Leave empty to include all VMs.",
                        max_length=255,
                    ),
                ),
                ("exclude_name_regex", models.CharField(blank=True, help_text="Skip matching VM names.", max_length=255)),
                ("sync_powered_off", models.BooleanField(default=True, verbose_name="Sync powered-off VMs")),
                ("sync_interfaces", models.BooleanField(default=True)),
                ("sync_ip_addresses", models.BooleanField(default=True)),
                ("sync_primary_ips", models.BooleanField(default=True)),
                ("update_existing", models.BooleanField(default=True, help_text="Update existing VMs matched by name and cluster.")),
                (
                    "default_ipv4_prefix_length",
                    models.PositiveSmallIntegerField(
                        default=24,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(32),
                        ],
                    ),
                ),
                (
                    "default_ipv6_prefix_length",
                    models.PositiveSmallIntegerField(
                        default=64,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(128),
                        ],
                    ),
                ),
                (
                    "sync_interval_minutes",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Optional automatic sync interval in minutes. Leave empty for manual sync only.",
                        null=True,
                        validators=[django.core.validators.MinValueValidator(5)],
                    ),
                ),
                ("next_sync_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("last_sync_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("last_success_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "last_status",
                    models.CharField(
                        choices=[
                            ("never", "Never synced"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                        ],
                        default="never",
                        editable=False,
                        max_length=30,
                    ),
                ),
                ("last_message", models.CharField(blank=True, editable=False, max_length=500)),
                ("last_vm_count", models.PositiveIntegerField(default=0, editable=False)),
                ("last_created_count", models.PositiveIntegerField(default=0, editable=False)),
                ("last_updated_count", models.PositiveIntegerField(default=0, editable=False)),
                ("last_error_count", models.PositiveIntegerField(default=0, editable=False)),
                ("comments", models.TextField(blank=True)),
                (
                    "cluster",
                    models.ForeignKey(
                        help_text="NetBox cluster into which VMware VMs will be synchronized.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="vmware_import_endpoints",
                        to="virtualization.cluster",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="vmware_import_endpoints",
                        to="dcim.site",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="vmware_import_endpoints",
                        to="tenancy.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "vCenter endpoint",
                "verbose_name_plural": "vCenter endpoints",
                "ordering": ("name",),
            },
        ),
    ]
