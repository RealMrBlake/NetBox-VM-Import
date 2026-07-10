import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn, ChoiceFieldColumn

from .models import VCenterEndpoint


class VCenterEndpointTable(NetBoxTable):
    name = tables.Column(
        linkify=True,
    )
    enabled = BooleanColumn()
    provider = ChoiceFieldColumn()
    tenant = tables.Column(
        linkify=True,
    )
    site = tables.Column(
        linkify=True,
    )
    cluster = tables.Column(
        linkify=True,
    )
    last_status = ChoiceFieldColumn(
        verbose_name=_("Last status"),
    )

    class Meta(NetBoxTable.Meta):
        model = VCenterEndpoint
        fields = (
            "pk",
            "id",
            "name",
            "enabled",
            "provider",
            "host",
            "tenant",
            "site",
            "cluster",
            "sync_interval_minutes",
            "next_sync_at",
            "last_status",
            "last_sync_at",
            "last_success_at",
        )
        default_columns = (
            "pk",
            "name",
            "enabled",
            "provider",
            "host",
            "tenant",
            "cluster",
            "last_status",
            "last_sync_at",
        )
