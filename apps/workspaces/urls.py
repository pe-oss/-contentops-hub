from django.urls import path

from .views import (
    WorkspaceCreateView,
    WorkspaceDetailView,
    WorkspaceListView,
    WorkspaceSwitchView,
    WorkspaceUpdateView,
)

app_name = "workspaces"

urlpatterns = [
    path("", WorkspaceListView.as_view(), name="list"),
    path("new/", WorkspaceCreateView.as_view(), name="create"),
    path("<uuid:workspace_id>/", WorkspaceDetailView.as_view(), name="detail"),
    path("<uuid:workspace_id>/edit/", WorkspaceUpdateView.as_view(), name="edit"),
    path("<uuid:workspace_id>/switch/", WorkspaceSwitchView.as_view(), name="switch"),
]
