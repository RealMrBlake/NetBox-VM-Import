from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from dcim.models import Site
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from tenancy.models import Tenant
from utilities.forms.fields import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    SlugField,
)
from utilities.forms.rendering import FieldSet
from virtualization.models import Cluster

from .choices import EndpointAuthMethodChoices, EndpointProviderChoices, SyncStatusChoices
from .models import VCenterEndpoint


class VCenterEndpointForm(NetBoxModelForm):
    slug = SlugField()
    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
    )
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
    )
    cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
    )
    provider = forms.ChoiceField(
        choices=EndpointProviderChoices,
        required=True,
    )
    auth_method = forms.ChoiceField(
        choices=EndpointAuthMethodChoices,
        required=True,
    )
    password = forms.CharField(
        label=_("Password / token secret"),
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_("Leave blank to keep the currently stored password."),
    )

    fieldsets = (
        FieldSet("name", "slug", "enabled", "comments", name=_("Endpoint")),
        FieldSet("provider", "host", "port", "username", "auth_method", "token_name", "password", "validate_ssl", name=_("Connection")),
        FieldSet("tenant", "site", "cluster", name=_("NetBox target")),
        FieldSet(
            "include_name_regex",
            "exclude_name_regex",
            "sync_powered_off",
            "sync_interfaces",
            "sync_ip_addresses",
            "sync_primary_ips",
            "sync_lxc_containers",
            "update_existing",
            name=_("Sync behavior"),
        ),
        FieldSet("default_ipv4_prefix_length", "default_ipv6_prefix_length", "sync_interval_minutes", name=_("Automation")),
        FieldSet("tags", name=_("Tags")),
    )

    class Meta:
        model = VCenterEndpoint
        fields = (
            "name",
            "slug",
            "enabled",
            "provider",
            "host",
            "port",
            "username",
            "auth_method",
            "token_name",
            "password",
            "validate_ssl",
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
            "comments",
            "tags",
        )

    def clean(self):
        super().clean()
        password = self.cleaned_data.get("password")

        if not self.instance.pk and not password:
            raise ValidationError({"password": _("A password is required for new endpoints.")})

        return self.cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)
        password = self.cleaned_data.get("password")

        if password:
            obj.set_password(password)

        if commit:
            obj.save()
            self.save_m2m()

        return obj


class VCenterEndpointFilterForm(NetBoxModelFilterSetForm):
    model = VCenterEndpoint

    enabled = forms.NullBooleanField(
        required=False,
        label=_("Enabled"),
    )

    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label=_("Site"),
    )
    cluster_id = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label=_("Cluster"),
    )
    last_status = forms.MultipleChoiceField(
        choices=SyncStatusChoices,
        required=False,
        label=_("Last status"),
    )
    provider = forms.MultipleChoiceField(
        choices=EndpointProviderChoices,
        required=False,
        label=_("Provider"),
    )

    fieldsets = (
        FieldSet("q", "enabled", "provider", "tenant_id", "site_id", "cluster_id", "last_status", name=_("Endpoint")),
    )
