import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_vmware_importer", "0002_align_netbox_46_model_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="host",
            field=models.CharField(help_text="vCenter, ESXi, or Proxmox VE hostname or IP address", max_length=255),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="validate_ssl",
            field=models.BooleanField(default=False, help_text="Validate the endpoint TLS certificate."),
        ),
        migrations.AlterField(
            model_name="vcenterendpoint",
            name="cluster",
            field=models.ForeignKey(
                help_text="NetBox cluster into which hypervisor VMs will be synchronized.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vmware_import_endpoints",
                to="virtualization.cluster",
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="provider",
            field=models.CharField(
                choices=[
                    ("vmware", "VMware vSphere"),
                    ("proxmox", "Proxmox VE"),
                ],
                default="vmware",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="auth_method",
            field=models.CharField(
                choices=[
                    ("password", "Username/password"),
                    ("api_token", "API token"),
                ],
                default="password",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="token_name",
            field=models.CharField(
                blank=True,
                help_text="Proxmox API token ID, e.g. netbox-import. The token secret is stored in the password field.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="vcenterendpoint",
            name="sync_lxc_containers",
            field=models.BooleanField(default=True, verbose_name="Sync Proxmox LXC containers"),
        ),
    ]
