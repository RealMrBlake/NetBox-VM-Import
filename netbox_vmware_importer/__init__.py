from netbox.plugins import PluginConfig


class VMwareImporterConfig(PluginConfig):
    name = "netbox_vmware_importer"
    verbose_name = "NetBox VMware Importer"
    description = "Synchronize VMware vSphere virtual machines into NetBox."
    version = "0.3.2"
    author = "Codex & Claude"
    base_url = "vmware-importer"
    min_version = "4.6.5"
    max_version = "4.7.99"

    def ready(self):
        super().ready()

        # Importing registers the scheduler system job with NetBox.
        from . import jobs  # noqa: F401
        from . import signals  # noqa: F401


config = VMwareImporterConfig
