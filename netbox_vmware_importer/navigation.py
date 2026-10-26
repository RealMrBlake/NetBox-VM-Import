from django.utils.translation import gettext_lazy as _
from netbox.choices import ButtonColorChoices
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


endpoint_item = PluginMenuItem(
    link="plugins:netbox_vmware_importer:vcenterendpoint_list",
    link_text=_("Endpoints"),
    permissions=["netbox_vmware_importer.view_vcenterendpoint"],
    buttons=(
        PluginMenuButton(
            "plugins:netbox_vmware_importer:vcenterendpoint_add",
            _("Add"),
            "mdi mdi-plus-thick",
            ButtonColorChoices.GREEN,
            permissions=["netbox_vmware_importer.add_vcenterendpoint"],
        ),
    ),
)

menu = PluginMenu(
    label=_("VMware Import"),
    groups=(
        (_("VMware"), (endpoint_item,)),
    ),
    icon_class="mdi mdi-cloud-sync",
)
