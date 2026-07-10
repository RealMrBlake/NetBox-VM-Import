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
