from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.views import generic

from .filtersets import VCenterEndpointFilterSet
from .forms import VCenterEndpointFilterForm, VCenterEndpointForm
from .jobs import SyncVCenterEndpointJob
from .models import VCenterEndpoint
from .tables import VCenterEndpointTable


class VCenterEndpointListView(generic.ObjectListView):
    queryset = VCenterEndpoint.objects.all()
    table = VCenterEndpointTable
    filterset = VCenterEndpointFilterSet
    filterset_form = VCenterEndpointFilterForm


class VCenterEndpointView(generic.ObjectView):
    queryset = VCenterEndpoint.objects.all()

    def get_extra_context(self, request, instance):
        return {
            "latest_jobs": instance.get_latest_jobs()[:10],
        }


class VCenterEndpointEditView(generic.ObjectEditView):
    queryset = VCenterEndpoint.objects.all()
    form = VCenterEndpointForm


class VCenterEndpointDeleteView(generic.ObjectDeleteView):
    queryset = VCenterEndpoint.objects.all()


class VCenterEndpointSyncView(View):
    def post(self, request, pk):
        endpoint = get_object_or_404(VCenterEndpoint, pk=pk)

        if not request.user.has_perm("netbox_vmware_importer.change_vcenterendpoint"):
            return HttpResponseForbidden()

        SyncVCenterEndpointJob.enqueue(instance=endpoint)
        endpoint.mark_queued()
        messages.success(request, _("VM sync job queued for %(endpoint)s.") % {"endpoint": endpoint})

        return redirect(endpoint)
