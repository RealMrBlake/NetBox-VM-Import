import re
from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from .choices import EndpointAuthMethodChoices, EndpointProviderChoices, SyncStatusChoices
from .crypto import decrypt_secret, encrypt_secret


class VCenterEndpoint(JobsMixin, NetBoxModel):
    name = models.CharField(
        max_length=100,
        unique=True,
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
    )
    enabled = models.BooleanField(
        default=True,
    )
    provider = models.CharField(
        max_length=30,
        choices=EndpointProviderChoices,
        default=EndpointProviderChoices.PROVIDER_VMWARE,
    )
    host = models.CharField(
        max_length=255,
        help_text=_("vCenter, ESXi, or Proxmox VE hostname or IP address"),
    )
    port = models.PositiveIntegerField(
        default=443,
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
    )
    username = models.CharField(
        max_length=255,
    )
    auth_method = models.CharField(
        max_length=30,
        choices=EndpointAuthMethodChoices,
        default=EndpointAuthMethodChoices.METHOD_PASSWORD,
    )
    token_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_("Proxmox API token ID, e.g. netbox-import. The token secret is stored in the password field."),
    )
    password_ciphertext = models.TextField(
        blank=True,
        editable=False,
    )
    validate_ssl = models.BooleanField(
        default=False,
        help_text=_("Validate the endpoint TLS certificate."),
    )
    request_timeout_seconds = models.PositiveIntegerField(
        default=120,
        validators=[MinValueValidator(5), MaxValueValidator(600)],
        help_text=_("HTTP/API read timeout in seconds."),
    )
    connect_timeout_seconds = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text=_("TCP/TLS connection timeout in seconds."),
    )
    max_retries = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_("Retries for safe Proxmox GET requests when the endpoint returns transient errors."),
    )
    retry_backoff_seconds = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.50"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("60.00"))],
        help_text=_("Exponential retry backoff base delay in seconds."),
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.PROTECT,
        related_name="vmware_import_endpoints",
        blank=True,
        null=True,
    )
    site = models.ForeignKey(
        to="dcim.Site",
        on_delete=models.PROTECT,
        related_name="vmware_import_endpoints",
        blank=True,
        null=True,
    )
    cluster = models.ForeignKey(
        to="virtualization.Cluster",
        on_delete=models.PROTECT,
        related_name="vmware_import_endpoints",
        help_text=_("NetBox cluster into which hypervisor VMs will be synchronized."),
    )
    include_name_regex = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Only synchronize matching VM names. Leave empty to include all VMs."),
    )
    exclude_name_regex = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Skip matching VM names."),
    )
    sync_powered_off = models.BooleanField(
        default=True,
        verbose_name=_("Sync powered-off VMs"),
    )
    sync_interfaces = models.BooleanField(
        default=True,
    )
    sync_ip_addresses = models.BooleanField(
        default=True,
    )
    sync_primary_ips = models.BooleanField(
        default=True,
    )
    sync_lxc_containers = models.BooleanField(
        default=True,
        verbose_name=_("Sync Proxmox LXC containers"),
    )
    update_existing = models.BooleanField(
        default=True,
        help_text=_("Update existing VMs matched by name and cluster."),
    )
    default_ipv4_prefix_length = models.PositiveSmallIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(32)],
    )
    default_ipv6_prefix_length = models.PositiveSmallIntegerField(
        default=64,
        validators=[MinValueValidator(1), MaxValueValidator(128)],
    )
    sync_interval_minutes = models.PositiveIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(5)],
        help_text=_("Optional automatic sync interval in minutes. Leave empty for manual sync only."),
    )
    next_sync_at = models.DateTimeField(
        blank=True,
        null=True,
        editable=False,
    )
    last_sync_at = models.DateTimeField(
        blank=True,
        null=True,
        editable=False,
    )
    last_success_at = models.DateTimeField(
        blank=True,
        null=True,
        editable=False,
    )
    last_status = models.CharField(
        max_length=30,
        choices=SyncStatusChoices,
        default=SyncStatusChoices.STATUS_NEVER,
        editable=False,
    )
    last_message = models.CharField(
        max_length=500,
        blank=True,
        editable=False,
    )
    last_vm_count = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    last_created_count = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    last_updated_count = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    last_error_count = models.PositiveIntegerField(
        default=0,
        editable=False,
    )
    comments = models.TextField(
        blank=True,
    )

    clone_fields = (
        "enabled",
        "provider",
        "host",
        "port",
        "username",
        "auth_method",
        "token_name",
        "validate_ssl",
        "request_timeout_seconds",
        "connect_timeout_seconds",
        "max_retries",
        "retry_backoff_seconds",
        "tenant",
        "site",
        "cluster",
        "include_name_regex",
        "exclude_name_regex",
        "sync_powered_off",
        "sync_interfaces",
        "sync_ip_addresses",
        "sync_primary_ips",
        "sync_lxc_containers",
        "update_existing",
        "default_ipv4_prefix_length",
        "default_ipv6_prefix_length",
        "sync_interval_minutes",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("virtualization endpoint")
        verbose_name_plural = _("virtualization endpoints")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_vmware_importer:vcenterendpoint", args=[self.pk])

    @property
    def password(self):
        return decrypt_secret(self.password_ciphertext)

    def set_password(self, value):
        self.password_ciphertext = encrypt_secret(value)

    def clean(self):
        super().clean()

        for field_name in ("include_name_regex", "exclude_name_regex"):
            pattern = getattr(self, field_name)
            if not pattern:
                continue
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValidationError({field_name: _("Invalid regular expression: %(error)s") % {"error": exc}})

        if self.site_id and self.cluster_id and getattr(self.cluster, "site_id", None):
            if self.cluster.site_id != self.site_id:
                raise ValidationError({"cluster": _("Selected cluster belongs to a different site.")})

        if self.provider == EndpointProviderChoices.PROVIDER_VMWARE:
            if self.auth_method != EndpointAuthMethodChoices.METHOD_PASSWORD:
                raise ValidationError({"auth_method": _("VMware endpoints currently support username/password authentication only.")})

        if self.provider == EndpointProviderChoices.PROVIDER_PROXMOX:
            if "@" not in self.username:
                raise ValidationError({"username": _("Proxmox usernames must include a realm, e.g. root@pam or user@pve.")})
            if self.auth_method == EndpointAuthMethodChoices.METHOD_API_TOKEN and not self.token_name:
                raise ValidationError({"token_name": _("A token name is required for Proxmox API token authentication.")})

    def mark_queued(self):
        self.last_status = SyncStatusChoices.STATUS_QUEUED
        self.last_message = _("Sync job queued.")
        self.save(update_fields=("last_status", "last_message", "last_updated"))

    def mark_running(self):
        self.last_sync_at = timezone.now()
        self.last_status = SyncStatusChoices.STATUS_RUNNING
        self.last_message = _("Sync job running.")
        self.save(update_fields=("last_sync_at", "last_status", "last_message", "last_updated"))

    def mark_success(self, result):
        now = timezone.now()
        self.last_sync_at = now
        self.last_success_at = now
        self.last_status = SyncStatusChoices.STATUS_SUCCESS
        self.last_vm_count = result.seen
        self.last_created_count = result.created
        self.last_updated_count = result.updated
        self.last_error_count = result.errors
        self.last_message = _(
            "Synchronized %(synced)s VM(s), skipped %(skipped)s VM(s)."
        ) % {"synced": result.synced, "skipped": result.skipped}
        self.set_next_sync(now)
        self.save(
            update_fields=(
                "last_sync_at",
                "last_success_at",
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

    def mark_failure(self, message):
        now = timezone.now()
        self.last_sync_at = now
        self.last_status = SyncStatusChoices.STATUS_FAILED
        self.last_message = str(message)[:500]
        self.set_next_sync(now)
        self.save(update_fields=("last_sync_at", "last_status", "last_message", "next_sync_at", "last_updated"))

    def set_next_sync(self, now=None):
        if self.enabled and self.sync_interval_minutes:
            self.next_sync_at = (now or timezone.now()) + timedelta(minutes=self.sync_interval_minutes)
        else:
            self.next_sync_at = None

    def save(self, *args, **kwargs):
        if not self.enabled or not self.sync_interval_minutes:
            self.next_sync_at = None
        elif not self.next_sync_at:
            self.set_next_sync()
        return super().save(*args, **kwargs)
