from netbox.plugins import PluginConfig


class VMwareImporterConfig(PluginConfig):
    name = "netbox_vmware_importer"
    verbose_name = "VMware Importer"
    description = "Synchronize VMware vSphere virtual machines into NetBox."
    version = "0.1.3"
    author = "Internal NetBox Team"
    base_url = "vmware-importer"
    min_version = "4.4.0"

    def ready(self):
        super().ready()

        # Importing registers the scheduler system job with NetBox.
        from . import jobs  # noqa: F401


config = VMwareImporterConfig
