from django.db.models import Q
import django_filters
from dcim.models import Site
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from virtualization.models import Cluster

from .choices import SyncStatusChoices
from .models import VCenterEndpoint


class VCenterEndpointFilterSet(NetBoxModelFilterSet):
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        field_name="tenant",
        queryset=Tenant.objects.all(),
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name="site",
        queryset=Site.objects.all(),
    )
    cluster_id = django_filters.ModelMultipleChoiceFilter(
        field_name="cluster",
        queryset=Cluster.objects.all(),
    )
    last_status = django_filters.MultipleChoiceFilter(
        choices=SyncStatusChoices,
    )

    class Meta:
        model = VCenterEndpoint
        fields = (
            "id",
            "name",
            "slug",
            "enabled",
            "host",
            "tenant_id",
            "site_id",
            "cluster_id",
            "last_status",
        )

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset

        return queryset.filter(
            Q(name__icontains=value)
            | Q(slug__icontains=value)
            | Q(host__icontains=value)
            | Q(username__icontains=value)
            | Q(comments__icontains=value)
        )
