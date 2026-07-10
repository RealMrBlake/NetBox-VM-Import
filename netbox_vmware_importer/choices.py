from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class SyncStatusChoices(ChoiceSet):
    STATUS_NEVER = "never"
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    CHOICES = [
        (STATUS_NEVER, _("Never synced"), "gray"),
        (STATUS_QUEUED, _("Queued"), "blue"),
        (STATUS_RUNNING, _("Running"), "cyan"),
        (STATUS_SUCCESS, _("Success"), "green"),
        (STATUS_FAILED, _("Failed"), "red"),
    ]


class EndpointProviderChoices(ChoiceSet):
    PROVIDER_VMWARE = "vmware"
    PROVIDER_PROXMOX = "proxmox"

    CHOICES = [
        (PROVIDER_VMWARE, _("VMware vSphere"), "blue"),
        (PROVIDER_PROXMOX, _("Proxmox VE"), "orange"),
    ]


class EndpointAuthMethodChoices(ChoiceSet):
    METHOD_PASSWORD = "password"
    METHOD_API_TOKEN = "api_token"

    CHOICES = [
        (METHOD_PASSWORD, _("Username/password"), "blue"),
        (METHOD_API_TOKEN, _("API token"), "green"),
    ]
