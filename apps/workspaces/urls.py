from django.urls import path

from .views import (
    BrandProfileView,
    ContentItemCreateView,
    ContentItemDetailView,
    ContentItemOwnerApproveView,
    ContentItemOwnerRequestChangesView,
    ContentItemWithdrawReviewView,
    ContentItemReopenView,
    ContentItemCancelView,
    ContentItemBlockView,
    ContentItemUnblockView,
    ContentItemRecordPublicationView,
    ContentPublicationEditView,
    ContentItemEditorVersionView,
    ContentItemRequestChangesView,
    ContentItemSaveDraftView,
    ContentItemStartWritingView,
    ContentItemSubmitReviewView,
    ContentItemSubmitVersionView,
    ContentItemUpdateView,
    InvitationAcceptView,
    MemberDeactivateView,
    MemberEditView,
    MemberReactivateView,
    PackageApprovePlanView,
    PackageCreateView,
    PackageDetailView,
    MyTasksView,
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
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/owner-approve/",
        ContentItemOwnerApproveView.as_view(),
        name="item_owner_approve",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/owner-request-changes/",
        ContentItemOwnerRequestChangesView.as_view(),
        name="item_owner_request_changes",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/withdraw-review/",
        ContentItemWithdrawReviewView.as_view(),
        name="item_withdraw_review",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/reopen/",
        ContentItemReopenView.as_view(),
        name="item_reopen",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/cancel/",
        ContentItemCancelView.as_view(),
        name="item_cancel",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/publications/",
        ContentItemRecordPublicationView.as_view(),
        name="item_record_publication",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/publications/<uuid:publication_id>/edit/",
        ContentPublicationEditView.as_view(),
        name="publication_edit_metadata",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/block/",
        ContentItemBlockView.as_view(),
        name="item_block",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/unblock/",
        ContentItemUnblockView.as_view(),
        name="item_unblock",
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
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/",
        ContentItemDetailView.as_view(),
        name="item_detail",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/start-writing/",
        ContentItemStartWritingView.as_view(),
        name="item_start_writing",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/save-draft/",
        ContentItemSaveDraftView.as_view(),
        name="item_save_draft",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/submit-version/",
        ContentItemSubmitVersionView.as_view(),
        name="item_submit_version",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/editor-version/",
        ContentItemEditorVersionView.as_view(),
        name="item_editor_version",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/request-changes/",
        ContentItemRequestChangesView.as_view(),
        name="item_request_changes",
    ),
    path(
        "<uuid:workspace_id>/packages/<uuid:package_id>/items/<uuid:item_id>/submit-review/",
        ContentItemSubmitReviewView.as_view(),
        name="item_submit_review",
    ),
    path(
        "<uuid:workspace_id>/my-tasks/",
        MyTasksView.as_view(),
        name="my_tasks",
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

