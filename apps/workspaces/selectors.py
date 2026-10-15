import uuid
from typing import Any
from django.contrib.auth import get_user_model
from django.db.models import Case, Count, F, IntegerField, Q, QuerySet, Value, When
from django.http import Http404
from django.utils import timezone

from .models import (
    AccessRole, AssignmentHistory, BrandProfile, ContentApproval, ContentItem, ContentItemState,
    ContentPublication, ContentVersion, Membership, MembershipStatus, Notification, NotificationEventType,
    Package, PackageStatus, ReviewDecision, Task, TaskRole, TaskStatus, Workspace,
)

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
    role_filter: str | None = None,
    package_id: uuid.UUID | str | None = None,
) -> QuerySet[Task]:
    """
    Lấy danh sách nhiệm vụ tác nghiệp được phân công cho người dùng trong workspace (Spec UI06, B05, B09).
    Chỉ lấy các nhiệm vụ thuộc workspace và do membership của người dùng phụ trách.
    Ưu tiên sắp xếp (Spec UI06):
    1. Bị chặn (item__is_blocked)
    2. Trễ hạn (is_overdue)
    3. Đến hạn gần nhất (due_at)
    """
    now = timezone.now()
    is_blocked_expr = Case(
        When(~Q(item__blocked_reason="") & Q(item__blocked_reason__isnull=False), then=Value(1)),
        default=Value(0),
        output_field=IntegerField(),
    )
    is_overdue_expr = Case(
        When(
            ~Q(status__in=[TaskStatus.DONE, TaskStatus.CANCELLED]) & Q(due_at__lt=now),
            then=Value(1),
        ),
        default=Value(0),
        output_field=IntegerField(),
    )

    qs = (
        Task.objects.filter(
            workspace=workspace,
            assignee_membership__user=user,
            assignee_membership__status=MembershipStatus.ACTIVE,
        )
        .annotate(is_blocked_val=is_blocked_expr, is_overdue=is_overdue_expr)
        .select_related("item", "item__package", "assignee_membership__user")
        .order_by("-is_blocked_val", "-is_overdue", "due_at", "-created_at")
    )
    if status_filter:
        qs = qs.filter(status=status_filter)
    if role_filter:
        qs = qs.filter(role=role_filter)
    if package_id:
        try:
            if isinstance(package_id, str):
                package_id = uuid.UUID(package_id)
            qs = qs.filter(item__package_id=package_id)
        except (ValueError, AttributeError):
            pass
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




def _get_dashboard_scope(workspace: Workspace, membership: Membership):
    """Xác định danh sách packages và items được phép đọc theo vai trò."""
    is_owner = membership.access_role == AccessRole.OWNER
    coord_pkg_ids = list(Package.objects.filter(workspace=workspace, coordinator_membership=membership).values_list("id", flat=True))
    assigned_q = Q(writer_membership=membership) | Q(editor_membership=membership) | Q(publisher_membership=membership)
    assigned_item_ids = list(ContentItem.objects.filter(workspace=workspace).filter(assigned_q).values_list("id", flat=True))

    if is_owner:
        return Package.objects.filter(workspace=workspace), ContentItem.objects.filter(workspace=workspace), coord_pkg_ids
    if coord_pkg_ids:
        pkgs = Package.objects.filter(Q(workspace=workspace) & (Q(id__in=coord_pkg_ids) | Q(items__id__in=assigned_item_ids))).distinct()
        items = ContentItem.objects.filter(Q(workspace=workspace) & (Q(package_id__in=coord_pkg_ids) | Q(id__in=assigned_item_ids))).distinct()
        return pkgs, items, coord_pkg_ids
    pkgs = Package.objects.filter(workspace=workspace, items__id__in=assigned_item_ids).distinct()
    items = ContentItem.objects.filter(workspace=workspace, id__in=assigned_item_ids)
    return pkgs, items, coord_pkg_ids


def get_workspace_dashboard_data(workspace: Workspace, user: Any) -> dict[str, Any]:
    """Tổng hợp dữ liệu Dashboard UI01 theo ba vùng (Spec mục 7 UI01, 8, 9, 13 B09)."""
    membership = get_active_membership(user, workspace)
    if not membership:
        raise Http404("Bạn không có quyền truy cập workspace này.")

    now = timezone.now()
    is_owner = membership.access_role == AccessRole.OWNER
    scoped_pkgs, scoped_items, coord_pkg_ids = _get_dashboard_scope(workspace, membership)
    is_coord = bool(coord_pkg_ids)

    overdue_q = (
        (Q(state__in=[ContentItemState.TODO, ContentItemState.WRITING]) & Q(writing_deadline__lt=now))
        | (Q(state=ContentItemState.EDITING) & Q(editing_deadline__lt=now))
        | (Q(state=ContentItemState.OWNER_REVIEW) & Q(review_deadline__lt=now))
        | (Q(state=ContentItemState.READY_TO_PUBLISH) & Q(planned_publish_at__lt=now))
    )

    draft_packages = []
    items_need_decision = []
    if is_owner:
        draft_packages = list(scoped_pkgs.filter(status=PackageStatus.DRAFT).select_related("coordinator_membership__user").order_by("created_at")[:10])
        items_need_decision = list(scoped_items.filter(state=ContentItemState.OWNER_REVIEW).select_related("package", "writer_membership__user", "editor_membership__user").order_by("review_deadline", "-created_at")[:10])
    elif is_coord:
        items_need_decision = list(scoped_items.filter(package_id__in=coord_pkg_ids, state__in=[ContentItemState.EDITING, ContentItemState.OWNER_REVIEW]).select_related("package", "writer_membership__user", "editor_membership__user").order_by("editing_deadline", "review_deadline")[:10])

    my_ready_tasks = list(Task.objects.filter(workspace=workspace, assignee_membership=membership, status=TaskStatus.READY).select_related("item", "item__package").order_by("due_at")[:10])
    blocked_q = ~Q(blocked_reason="") & Q(blocked_reason__isnull=False)
    blocked_items = list(scoped_items.filter(blocked_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).select_related("package", "blocked_by", "writer_membership__user", "editor_membership__user").order_by("-blocked_at")[:10])
    overdue_items = list(scoped_items.filter(overdue_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).select_related("package", "writer_membership__user", "editor_membership__user", "publisher_membership__user").order_by("writing_deadline", "editing_deadline", "review_deadline", "planned_publish_at")[:10])

    packages_progress = list(scoped_pkgs.annotate(total_items_count=Count("items"), published_items_count=Count("items", filter=Q(items__state=ContentItemState.PUBLISHED)), cancelled_items_count=Count("items", filter=Q(items__state=ContentItemState.CANCELLED))).select_related("coordinator_membership__user").order_by("-created_at")[:20])
    for p in packages_progress:
        p.active_items_count = max(p.total_items_count - p.cancelled_items_count, 0)
        p.progress_display = f"{p.published_items_count}/{p.active_items_count} bài đã đăng"

    if is_owner:
        stats = {
            "active_packages_count": scoped_pkgs.filter(status=PackageStatus.ACTIVE).count(),
            "pending_approval_count": scoped_items.filter(state=ContentItemState.OWNER_REVIEW).count(),
            "blocked_items_count": scoped_items.filter(blocked_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).count(),
            "overdue_items_count": scoped_items.filter(overdue_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).count(),
            "published_items_count": scoped_items.filter(state=ContentItemState.PUBLISHED).count(),
        }
    elif is_coord:
        stats = {
            "active_packages_count": scoped_pkgs.filter(id__in=coord_pkg_ids, status=PackageStatus.ACTIVE).count(),
            "my_ready_tasks_count": len(my_ready_tasks),
            "blocked_items_count": scoped_items.filter(blocked_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).count(),
            "overdue_items_count": scoped_items.filter(overdue_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).count(),
            "published_items_count": scoped_items.filter(state=ContentItemState.PUBLISHED).count(),
        }
    else:
        my_tasks_base = Task.objects.filter(workspace=workspace, assignee_membership=membership)
        stats = {
            "my_ready_tasks_count": my_tasks_base.filter(status=TaskStatus.READY).count(),
            "my_in_progress_tasks_count": my_tasks_base.filter(status=TaskStatus.IN_PROGRESS).count(),
            "my_blocked_items_count": scoped_items.filter(blocked_q).exclude(state__in=[ContentItemState.CANCELLED, ContentItemState.PUBLISHED]).count(),
            "my_overdue_tasks_count": my_tasks_base.filter(~Q(status__in=[TaskStatus.DONE, TaskStatus.CANCELLED]), due_at__lt=now).count(),
            "my_done_tasks_count": my_tasks_base.filter(status=TaskStatus.DONE).count(),
        }

    return {
        "workspace": workspace, "membership": membership, "is_owner": is_owner, "is_coordinator": is_coord,
        "stats": stats, "draft_packages": draft_packages, "items_need_decision": items_need_decision,
        "my_ready_tasks": my_ready_tasks, "blocked_items": blocked_items, "overdue_items": overdue_items,
        "packages_progress": packages_progress,
    }



def user_has_entity_access(user: Any, workspace: Workspace, entity_type: str, entity_id: uuid.UUID | str) -> bool:
    """
    Kiểm tra xem người dùng hiện tại có còn quyền truy cập đối tượng thông báo hay không (Spec mục 8, B09):
    - Người dùng phải có membership ACTIVE trong workspace.
    - OWNER có toàn quyền truy cập.
    - Điều phối viên có quyền trong các gói mình phụ trách.
    - Thành viên có quyền nếu được phân công trong bài viết.
    - Nếu quyền đã bị thu hồi hoặc chuyển giao, trả về False.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    membership = get_active_membership(user, workspace)
    if not membership or not membership.is_active:
        return False

    if membership.access_role == AccessRole.OWNER:
        return True

    if isinstance(entity_id, str):
        try:
            entity_id = uuid.UUID(entity_id)
        except ValueError:
            return False

    if entity_type == "CONTENT_ITEM":
        item = ContentItem.objects.filter(id=entity_id, workspace=workspace).select_related("package").first()
        if not item:
            return False
        if item.package.coordinator_membership_id == membership.id:
            return True
        return (
            item.writer_membership_id == membership.id
            or item.editor_membership_id == membership.id
            or item.publisher_membership_id == membership.id
        )

    if entity_type == "PACKAGE":
        package = Package.objects.filter(id=entity_id, workspace=workspace).first()
        if not package:
            return False
        if package.coordinator_membership_id == membership.id:
            return True
        return ContentItem.objects.filter(package=package).filter(
            Q(writer_membership=membership) | Q(editor_membership=membership) | Q(publisher_membership=membership)
        ).exists()

    if entity_type == "TASK":
        task = Task.objects.filter(id=entity_id, workspace=workspace).select_related("item", "item__package").first()
        if not task:
            return True
        if task.item.package.coordinator_membership_id == membership.id:
            return True
        return task.assignee_membership_id == membership.id

    return True


def get_user_notifications(user: Any, workspace: Workspace | None = None, unread_only: bool = False) -> list[Notification]:
    """
    Lấy danh sách thông báo của người dùng kèm kiểm tra quyền đọc hiện tại (Spec mục 8, B09).
    Lọc quyền hiện tại: Nếu thành viên bị thu hồi hoặc mất quyền đối tượng, không hiển thị.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return []

    active_ws_ids = list(Membership.objects.filter(user=user, status=MembershipStatus.ACTIVE).values_list("workspace_id", flat=True))
    if not active_ws_ids:
        return []

    qs = Notification.objects.filter(recipient=user, workspace_id__in=active_ws_ids).select_related("workspace")
    if workspace:
        if workspace.id not in active_ws_ids:
            return []
        qs = qs.filter(workspace=workspace)

    if unread_only:
        qs = qs.filter(read_at__isnull=True)

    qs = qs.order_by("-created_at")

    valid_notifications = []
    for notif in qs:
        if user_has_entity_access(user, notif.workspace, notif.entity_type, notif.entity_id):
            valid_notifications.append(notif)

    return valid_notifications


def get_unread_notifications_count(user: Any, workspace: Workspace | None = None) -> int:
    """Số lượng thông báo chưa đọc đã lọc quyền hiện tại của người dùng (Spec mục 8, B09)."""
    return len(get_user_notifications(user, workspace=workspace, unread_only=True))

