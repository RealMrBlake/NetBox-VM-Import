from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .jobs import clear_endpoint_sync_schedule, schedule_endpoint_sync
from .models import VCenterEndpoint


AUTOMATIC_SYNC_FIELDS = {"enabled", "provider", "sync_interval_minutes"}


@receiver(post_save, sender=VCenterEndpoint)
def schedule_vcenter_endpoint_sync(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:
        return

    if update_fields is not None and not AUTOMATIC_SYNC_FIELDS.intersection(update_fields):
        return

    transaction.on_commit(lambda: schedule_endpoint_sync(instance))


@receiver(pre_delete, sender=VCenterEndpoint)
def clear_vcenter_endpoint_sync(sender, instance, **kwargs):
    clear_endpoint_sync_schedule(instance)
