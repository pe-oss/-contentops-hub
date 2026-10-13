import uuid
from typing import Any
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.http import Http404

from .models import Membership, MembershipStatus, Workspace

User = get_user_model()


def get_user_active_memberships(user: Any) -> QuerySet[Membership]:
    """
    Trả về danh sách memberships đang hoạt động của người dùng.
    """
    if not user or not user.is_authenticated:
        return Membership.objects.none()
    return (
        Membership.objects.filter(user=user, status=MembershipStatus.ACTIVE)
        .select_related("workspace")
        .order_by("-created_at")
    )


def get_user_workspaces(user: Any) -> QuerySet[Workspace]:
    """
    Trả về danh sách Workspaces mà người dùng có membership đang hoạt động (ACTIVE).
    Cách ly: Người dùng tuyệt đối không thấy workspace mà mình không có membership active.
    """
    if not user or not user.is_authenticated:
        return Workspace.objects.none()
    return (
        Workspace.objects.filter(
            memberships__user=user,
            memberships__status=MembershipStatus.ACTIVE,
        )
        .distinct()
        .order_by("-created_at")
    )


def get_active_membership(user: Any, workspace: Workspace) -> Membership | None:
    """
    Lấy membership ACTIVE của người dùng trong một workspace cụ thể.
    """
    if not user or not user.is_authenticated or not workspace:
        return None
    return Membership.objects.filter(
        user=user,
        workspace=workspace,
        status=MembershipStatus.ACTIVE,
    ).first()


def get_workspace_for_user(user: Any, workspace_id: uuid.UUID | str) -> tuple[Workspace, Membership]:
    """
    Tìm workspace theo UUID và xác thực quyền truy cập của người dùng.
    Quy tắc an ninh Spec 3.1:
    - Nếu workspace không tồn tại HOẶC người dùng không có membership ACTIVE:
      trả về HTTP 404 (không phân biệt để không làm lộ sự tồn tại của ID).
    """
    if not user or not user.is_authenticated:
        raise Http404("Workspace không tồn tại hoặc bạn không có quyền truy cập.")

    try:
        if isinstance(workspace_id, str):
            workspace_id = uuid.UUID(workspace_id)
    except (ValueError, AttributeError):
        raise Http404("Workspace không tồn tại hoặc bạn không có quyền truy cập.")

    try:
        workspace = Workspace.objects.get(id=workspace_id)
    except Workspace.DoesNotExist:
        raise Http404("Workspace không tồn tại hoặc bạn không có quyền truy cập.")

    membership = get_active_membership(user, workspace)
    if not membership:
        raise Http404("Workspace không tồn tại hoặc bạn không có quyền truy cập.")

    return workspace, membership

from .models import Invitation


def get_workspace_members(workspace: Workspace) -> QuerySet[Membership]:
    """
    Trả về danh sách tất cả thành viên trong workspace (kể cả ACTIVE và INACTIVE).
    """
    return (
        Membership.objects.filter(workspace=workspace)
        .select_related("user", "user__email_identity")
        .order_by("access_role", "created_at")
    )


def get_workspace_invitations(workspace: Workspace) -> QuerySet[Invitation]:
    """
    Trả về danh sách các lời mời của workspace.
    """
    return (
        Invitation.objects.filter(workspace=workspace)
        .select_related("invited_by")
        .order_by("-created_at")
    )


def get_invitation_by_token(raw_token: str) -> Invitation | None:
    """
    Tìm lời mời dựa trên raw token (băm SHA-256 để so khớp với token_hash trong DB).
    """
    if not raw_token or not raw_token.strip():
        return None

    import hashlib

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    return (
        Invitation.objects.filter(token_hash=token_hash)
        .select_related("workspace", "invited_by")
        .first()
    )


def get_invitation_by_id_for_workspace(
    workspace: Workspace,
    invitation_id: uuid.UUID | str,
) -> Invitation:
    """
    Lấy lời mời theo ID trong một workspace cụ thể. Nếu không thuộc workspace trả 404.
    """
    try:
        if isinstance(invitation_id, str):
            invitation_id = uuid.UUID(invitation_id)
    except (ValueError, AttributeError):
        raise Http404("Lời mời không tồn tại.")

    invitation = (
        Invitation.objects.filter(id=invitation_id, workspace=workspace)
        .select_related("workspace", "invited_by")
        .first()
    )
    if not invitation:
        raise Http404("Lời mời không tồn tại trong workspace này.")
    return invitation


def get_membership_by_id_for_workspace(
    workspace: Workspace,
    membership_id: uuid.UUID | str,
) -> Membership:
    """
    Lấy membership theo ID trong một workspace cụ thể. Nếu không thuộc workspace trả 404.
    """
    try:
        if isinstance(membership_id, str):
            membership_id = uuid.UUID(membership_id)
    except (ValueError, AttributeError):
        raise Http404("Thành viên không tồn tại.")

    membership = (
        Membership.objects.filter(id=membership_id, workspace=workspace)
        .select_related("user", "workspace")
        .first()
    )
    if not membership:
        raise Http404("Thành viên không tồn tại trong workspace này.")
    return membership

