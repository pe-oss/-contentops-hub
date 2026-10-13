from django.urls import path

from .views import (
    BrandProfileView,
    ContentItemCreateView,
    ContentItemUpdateView,
    InvitationAcceptView,
    MemberDeactivateView,
    MemberEditView,
    MemberReactivateView,
    PackageApprovePlanView,
    PackageCreateView,
    PackageDetailView,
    PackageListView,
    PackageUpdateView,
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

    # Packages & Planning (B04)
    path("<uuid:workspace_id>/packages/", PackageListView.as_view(), name="package_list"),
    path("<uuid:workspace_id>/packages/new/", PackageCreateView.as_view(), name="package_create"),
    path("<uuid:workspace_id>/packages/<uuid:package_id>/", PackageDetailView.as_view(), name="package_detail"),
    path("<uuid:workspace_id>/packages/<uuid:package_id>/edit/", PackageUpdateView.as_view(), name="package_edit"),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/approve-plan/",
        PackageApprovePlanView.as_view(),
        name="package_approve_plan",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/new/",
        ContentItemCreateView.as_view(),
        name="item_create",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/edit/",
        ContentItemUpdateView.as_view(),
        name="item_edit",
    ),

    # Members & Invitations (B02)
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

