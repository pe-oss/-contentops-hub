from django.urls import path

from .views import (
    BrandProfileView,
    InvitationAcceptView,
    MemberDeactivateView,
    MemberEditView,
    MemberReactivateView,
    WorkspaceCreateView,
    WorkspaceDetailView,
    WorkspaceInvitationResendView,
    WorkspaceInvitationRevokeView,
    WorkspaceInviteView,
    WorkspaceListView,
    WorkspaceMembersView,
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
    path("<uuid:workspace_id>/brand/", BrandProfileView.as_view(), name="brand_profile"),

    path("<uuid:workspace_id>/members/", WorkspaceMembersView.as_view(), name="members"),
    path("<uuid:workspace_id>/members/<uuid:membership_id>/edit/", MemberEditView.as_view(), name="member_edit"),
    path(
        "<uuid:workspace_id>/members/<uuid:membership_id>/deactivate/",
        MemberDeactivateView.as_view(),
        name="member_deactivate",
    ),
    path(
        "<uuid:workspace_id>/members/<uuid:membership_id>/reactivate/",
        MemberReactivateView.as_view(),
        name="member_reactivate",
    ),
    path("<uuid:workspace_id>/invitations/new/", WorkspaceInviteView.as_view(), name="invite"),
    path(
        "<uuid:workspace_id>/invitations/<uuid:invitation_id>/revoke/",
        WorkspaceInvitationRevokeView.as_view(),
        name="invitation_revoke",
    ),
    path(
        "<uuid:workspace_id>/invitations/<uuid:invitation_id>/resend/",
        WorkspaceInvitationResendView.as_view(),
        name="invitation_resend",
    ),
    path("invitations/accept/<str:token>/", InvitationAcceptView.as_view(), name="invitation_accept"),
]
