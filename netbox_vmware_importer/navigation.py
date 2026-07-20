from netbox.choices import ButtonColorChoices
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem


endpoint_item = PluginMenuItem(
    link="plugins:netbox_vmware_importer:vcenterendpoint_list",
    link_text="Endpoints",
    permissions=["netbox_vmware_importer.view_vcenterendpoint"],
    buttons=(
        PluginMenuButton(
            "plugins:netbox_vmware_importer:vcenterendpoint_add",
            "Add",
            "mdi mdi-plus-thick",
            ButtonColorChoices.GREEN,
            permissions=["netbox_vmware_importer.add_vcenterendpoint"],
        ),
    ),
)

menu = PluginMenu(
    label="VMware Import",
    groups=(
        ("VMware", (endpoint_item,)),
    ),
    icon_class="mdi mdi-cloud-sync",
)
