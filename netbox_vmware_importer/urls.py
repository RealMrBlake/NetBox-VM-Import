from django.urls import path
from netbox.views import generic

from . import views
from .models import VCenterEndpoint

urlpatterns = (
    path("vcenters/", views.VCenterEndpointListView.as_view(), name="vcenterendpoint_list"),
    path("vcenters/add/", views.VCenterEndpointEditView.as_view(), name="vcenterendpoint_add"),
    path("vcenters/<int:pk>/", views.VCenterEndpointView.as_view(), name="vcenterendpoint"),
    path("vcenters/<int:pk>/edit/", views.VCenterEndpointEditView.as_view(), name="vcenterendpoint_edit"),
    path("vcenters/<int:pk>/delete/", views.VCenterEndpointDeleteView.as_view(), name="vcenterendpoint_delete"),
    path("vcenters/<int:pk>/sync/", views.VCenterEndpointSyncView.as_view(), name="vcenterendpoint_sync"),
    path(
        "vcenters/<int:pk>/changelog/",
        generic.ObjectChangeLogView.as_view(),
        name="vcenterendpoint_changelog",
        kwargs={"model": VCenterEndpoint},
    ),
)
