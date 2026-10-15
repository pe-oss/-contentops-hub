import uuid
from typing import Any
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.http import Http404

from .models import BrandProfile, Membership, MembershipStatus, Workspace

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



def get_brand_profile(workspace: Workspace) -> BrandProfile | None:
    """
    Lấy hồ sơ thương hiệu của workspace nếu có.
    """
    if not workspace:
        return None
    return BrandProfile.objects.filter(workspace=workspace).select_related("updated_by").first()

from .models import AssignmentHistory, ContentApproval, ContentItem, ContentPublication, ContentVersion, Package, PackageStatus, ReviewDecision, Task, TaskStatus


def get_item_publications(item: ContentItem) -> QuerySet[ContentPublication]:
    """
    Lấy lịch sử xuất bản của bài viết (Spec F06, 9 B07), sắp xếp mới nhất trước.
    """
    return (
        ContentPublication.objects.filter(item=item)
        .select_related("version", "approval", "recorded_by")
        .order_by("-recorded_at")
    )


def get_item_active_approval(item: ContentItem) -> ContentApproval | None:
    """
    Lấy phê duyệt đang có hiệu lực của bài viết (Spec B06, 6.1, 6.3).
    Mỗi bài viết chỉ có tối đa một phê duyệt hợp lệ (invalidated_at__isnull=True).
    """
    return (
        ContentApproval.objects.filter(item=item, invalidated_at__isnull=True)
        .select_related("version", "approved_by")
        .first()
    )


def get_item_approvals(item: ContentItem) -> QuerySet[ContentApproval]:
    """
    Lấy lịch sử phê duyệt của bài viết (cả hợp lệ và đã bị vô hiệu khi mở lại).
    """
    return (
        ContentApproval.objects.filter(item=item)
        .select_related("version", "approved_by")
        .order_by("-approved_at")
    )
def get_workspace_packages(workspace: Workspace) -> QuerySet[Package]:
    """
    Lấy danh sách các Gói nội dung thuộc workspace.
    """
    return (
        Package.objects.filter(workspace=workspace)
        .select_related("coordinator_membership", "coordinator_membership__user")
        .order_by("-created_at")
    )


def get_item_versions(item: ContentItem) -> QuerySet[ContentVersion]:
    """
    Lấy danh sách các phiên bản nội dung của bài viết, sắp xếp từ mới nhất đến cũ nhất.
    """
    return (
        ContentVersion.objects.filter(item=item)
        .select_related("author_membership__user")
        .order_by("-version_no")
    )


def get_item_decisions(item: ContentItem) -> QuerySet[ReviewDecision]:
    """
    Lấy danh sách các quyết định biên tập/duyệt của bài viết theo thứ tự thời gian.
    """
    return (
        ReviewDecision.objects.filter(item=item)
        .select_related("actor_membership__user", "version")
        .order_by("-created_at")
    )


def get_my_tasks_for_workspace(
    workspace: Workspace,
    user: Any,
    status_filter: str | None = None,
) -> QuerySet[Task]:
    """
    Lấy danh sách nhiệm vụ tác nghiệp được phân công cho người dùng trong workspace (Spec UI06, B05).
    Chỉ lấy các nhiệm vụ thuộc workspace và do membership của người dùng phụ trách.
    """
    qs = (
        Task.objects.filter(
            workspace=workspace,
            assignee_membership__user=user,
            assignee_membership__status=MembershipStatus.ACTIVE,
        )
        .select_related("item", "item__package", "assignee_membership__user")
        .order_by("due_at", "-created_at")
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    return qs


def get_package_for_workspace(workspace: Workspace, package_id: uuid.UUID | str) -> Package:
    """
    Lấy chi tiết Gói nội dung theo ID trong một workspace cụ thể.
    Trả về 404 nếu không tìm thấy hoặc thuộc workspace khác (cách ly tenant).
    """
    try:
        if isinstance(package_id, str):
            package_id = uuid.UUID(package_id)
    except (ValueError, AttributeError):
        raise Http404("Gói nội dung không tồn tại.")

    package = (
        Package.objects.filter(id=package_id, workspace=workspace)
        .select_related("workspace", "coordinator_membership", "coordinator_membership__user")
        .first()
    )
    if not package:
        raise Http404("Gói nội dung không tồn tại trong workspace này.")
    return package


def get_package_items(package: Package) -> QuerySet[ContentItem]:
    """
    Lấy danh sách các bài viết trong một Gói nội dung.
    """
    return (
        ContentItem.objects.filter(package=package)
        .select_related(
            "writer_membership__user",
            "editor_membership__user",
            "publisher_membership__user",
        )
        .order_by("order", "created_at")
    )


def get_item_for_workspace(workspace: Workspace, item_id: uuid.UUID | str) -> ContentItem:
    """
    Lấy bài viết theo ID trong workspace. Trả về 404 nếu không thuộc workspace.
    """
    try:
        if isinstance(item_id, str):
            item_id = uuid.UUID(item_id)
    except (ValueError, AttributeError):
        raise Http404("Bài viết không tồn tại.")

    item = (
        ContentItem.objects.filter(id=item_id, workspace=workspace)
        .select_related(
            "package",
            "writer_membership__user",
            "editor_membership__user",
            "publisher_membership__user",
        )
        .first()
    )
    if not item:
        raise Http404("Bài viết không tồn tại trong workspace này.")
    return item


def get_item_tasks(item: ContentItem) -> QuerySet[Task]:
    """
    Lấy danh sách các nhiệm vụ của một bài viết.
    """
    return (
        Task.objects.filter(item=item)
        .select_related("assignee_membership__user")
        .order_by("role")
    )



def get_item_assignment_history(item: ContentItem) -> QuerySet[AssignmentHistory]:
    """
    Lấy toàn bộ lịch sử bàn giao/đổi người của bài viết (Spec F07, 7 UI05, 9, 13 B08),
    sắp xếp mới nhất trước.
    """
    return (
        AssignmentHistory.objects.filter(item=item)
        .select_related(
            "previous_assignee__user",
            "new_assignee__user",
            "reassigned_by",
            "task",
        )
        .order_by("-created_at")
    )


def get_member_open_tasks(membership: Membership) -> QuerySet[Task]:
    """
    Lấy toàn bộ nhiệm vụ đang mở (WAITING, READY, IN_PROGRESS) của một thành viên (Spec AC11).
    """
    return (
        Task.objects.filter(
            assignee_membership=membership,
            status__in=[TaskStatus.WAITING, TaskStatus.READY, TaskStatus.IN_PROGRESS],
        )
        .select_related("item", "item__package")
        .order_by("due_at", "created_at")
    )


def get_member_assigned_items(membership: Membership) -> QuerySet[ContentItem]:
    """
    Lấy các bài viết chưa kết thúc (không CANCELLED) mà thành viên được phân công làm
    người viết, biên tập, hoặc xuất bản (Spec AC11).
    """
    from django.db.models import Q
    from .models import ContentItemState
    return (
        ContentItem.objects.filter(
            Q(writer_membership=membership)
            | Q(editor_membership=membership)
            | Q(publisher_membership=membership),
            workspace=membership.workspace,
        )
        .exclude(state=ContentItemState.CANCELLED)
        .select_related("package")
        .order_by("created_at")
    )


def get_member_coordinated_packages(membership: Membership) -> QuerySet[Package]:
    """
    Lấy các gói nội dung đang mở (DRAFT hoặc ACTIVE) mà thành viên đang làm điều phối (Spec AC11).
    """
    return (
        Package.objects.filter(
            coordinator_membership=membership,
            workspace=membership.workspace,
            status__in=[PackageStatus.DRAFT, PackageStatus.ACTIVE],
        )
        .order_by("created_at")
    )

