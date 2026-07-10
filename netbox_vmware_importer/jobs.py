from core.exceptions import JobFailed
from django.utils import timezone
from netbox.jobs import JobRunner, system_job

from .choices import SyncStatusChoices
from .models import VCenterEndpoint
from .sync import VMwareImporter


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
            "VMware sync finished for %s: %s VM(s), %s created, %s updated, %s skipped.",
            endpoint.name,
            result.synced,
            result.created,
            result.updated,
            result.skipped,
        )


@system_job(interval=5)
class ScheduleDueVCenterSyncsJob(JobRunner):
    class Meta:
        name = "Schedule due VMware VM synchronizations"

    def run(self, *args, **kwargs):
        now = timezone.now()
        due_endpoints = VCenterEndpoint.objects.filter(
            enabled=True,
            sync_interval_minutes__isnull=False,
        ).filter(next_sync_at__lte=now)

        queued = 0
        for endpoint in due_endpoints:
            SyncVCenterEndpointJob.enqueue_once(instance=endpoint)
            endpoint.last_status = SyncStatusChoices.STATUS_QUEUED
            endpoint.last_message = "Automatic sync job queued."
            endpoint.set_next_sync(now)
            endpoint.save(update_fields=("last_status", "last_message", "next_sync_at", "last_updated"))
            queued += 1

        self.logger.info("Queued %s VMware sync job(s).", queued)
