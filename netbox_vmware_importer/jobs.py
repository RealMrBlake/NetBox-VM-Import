from core.choices import JobStatusChoices
from core.exceptions import JobFailed
from django.utils import timezone
from netbox.jobs import JobRunner, system_job

from .choices import SyncStatusChoices
from .models import VCenterEndpoint
from .sync import VMwareImporter


def clear_endpoint_sync_schedule(endpoint):
    return SyncVCenterEndpointJob.get_jobs(endpoint).filter(
        status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
        interval__isnull=False,
    ).delete()


def schedule_endpoint_sync(endpoint):
    if not endpoint.enabled or not endpoint.sync_interval_minutes:
        clear_endpoint_sync_schedule(endpoint)
        return None

    if not endpoint.next_sync_at:
        endpoint.next_sync_at = timezone.now()
        VCenterEndpoint.objects.filter(pk=endpoint.pk).update(next_sync_at=endpoint.next_sync_at)

    return SyncVCenterEndpointJob.enqueue_once(
        instance=endpoint,
        schedule_at=endpoint.next_sync_at,
        interval=endpoint.sync_interval_minutes,
    )


class SyncVCenterEndpointJob(JobRunner):
    class Meta:
        name = "VMware VM synchronization"

    def run(self, *args, **kwargs):
        endpoint = self.job.object
        if endpoint is None:
            endpoint_pk = kwargs.get("endpoint_pk")
            endpoint = VCenterEndpoint.objects.get(pk=endpoint_pk)

        if not endpoint.enabled:
            endpoint.mark_failure("Endpoint is disabled.")
            raise JobFailed("Endpoint is disabled.")

        self.logger.info("Starting VMware sync for %s (%s)", endpoint.name, endpoint.host)
        endpoint.mark_running()

        try:
            result = VMwareImporter(endpoint, self.logger).sync()
        except Exception as exc:
            endpoint.mark_failure(exc)
            raise

        if result.errors:
            endpoint.last_sync_at = timezone.now()
            endpoint.last_status = SyncStatusChoices.STATUS_FAILED
            endpoint.last_vm_count = result.seen
            endpoint.last_created_count = result.created
            endpoint.last_updated_count = result.updated
            endpoint.last_error_count = result.errors
            endpoint.last_status = SyncStatusChoices.STATUS_FAILED
            endpoint.last_message = f"Finished with {result.errors} VM error(s). Check the job log."
            endpoint.set_next_sync(endpoint.last_sync_at)
            endpoint.save(
                update_fields=(
                    "last_sync_at",
                    "last_status",
                    "last_vm_count",
                    "last_created_count",
                    "last_updated_count",
                    "last_error_count",
                    "last_message",
                    "next_sync_at",
                    "last_updated",
                )
            )
            raise JobFailed(endpoint.last_message)

        endpoint.mark_success(result)
        self.logger.info(
            (
                "VMware sync finished for %s: %s VM(s), %s created, %s updated, %s skipped; "
                "virtual disks: %s created, %s updated, %s deleted; "
                "MAC addresses: %s created, %s updated, %s deleted."
            ),
            endpoint.name,
            result.synced,
            result.created,
            result.updated,
            result.skipped,
            result.virtual_disks_created,
            result.virtual_disks_updated,
            result.virtual_disks_deleted,
            result.mac_addresses_created,
            result.mac_addresses_updated,
            result.mac_addresses_deleted,
        )


@system_job(interval=5)
class ScheduleDueVCenterSyncsJob(JobRunner):
    class Meta:
        name = "Schedule due VMware VM synchronizations"

    def run(self, *args, **kwargs):
        now = timezone.now()
        enabled_endpoints = VCenterEndpoint.objects.filter(
            enabled=True,
            sync_interval_minutes__isnull=False,
        )

        scheduled = 0
        for endpoint in enabled_endpoints:
            if endpoint.next_sync_at is None:
                endpoint.next_sync_at = now
                endpoint.save(update_fields=("next_sync_at", "last_updated"))
            if schedule_endpoint_sync(endpoint):
                scheduled += 1

        self.logger.info("Ensured %s VMware endpoint sync schedule(s).", scheduled)
