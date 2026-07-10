from netbox.plugins import PluginConfig


class VMwareImporterConfig(PluginConfig):
    name = "netbox_vmware_importer"
    verbose_name = "Virtualization Importer"
    description = "Synchronize VMware vSphere and Proxmox VE virtual machines into NetBox."
    version = "0.2.1"
    author = "Internal NetBox Team"
    base_url = "vmware-importer"
    min_version = "4.4.0"

    def ready(self):
        super().ready()

        # Importing registers the scheduler system job with NetBox.
        from . import jobs  # noqa: F401
        from . import signals  # noqa: F401


config = VMwareImporterConfig
