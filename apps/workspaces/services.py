import uuid
from typing import Any
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import AccessRole, EmploymentType, Membership, MembershipStatus, Workspace, validate_timezone
from .selectors import get_active_membership, get_user_workspaces, get_workspace_for_user

User = get_user_model()

ACTIVE_WORKSPACE_SESSION_KEY = "active_workspace_id"


def validate_workspace_input(name: str, timezone_str: str) -> tuple[str, str]:
    """
    Chuẩn hóa và kiểm tra tên và múi giờ theo Spec mục 4:
    - Tên 1-100 ký tự, strip khoảng trắng đầu/cuối, không chấp nhận chỉ khoảng trắng.
    - Múi giờ theo chuẩn IANA.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError({"name": "Tên workspace không được để trống."})
    if len(clean_name) > 100:
        raise ValidationError({"name": "Tên workspace không được vượt quá 100 ký tự."})

    clean_tz = (timezone_str or "").strip() or "Asia/Ho_Chi_Minh"
    validate_timezone(clean_tz)

    return clean_name, clean_tz


@transaction.atomic
def create_workspace_with_owner(
    *,
    user: Any,
    name: str,
    timezone_str: str = "Asia/Ho_Chi_Minh",
) -> Workspace:
    """
    Tạo workspace mới cùng membership OWNER đang hoạt động trong cùng một transaction.
    Đảm bảo tính nhất quán:
    - owner_user là nguồn xác định Chủ; membership OWNER gắn với user này.
    - Mỗi workspace có đúng một Chủ.
    - Nếu có bất kỳ lỗi nào, transaction được rollback toàn bộ.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Người dùng chưa đăng nhập không thể tạo workspace.")

    clean_name, clean_tz = validate_workspace_input(name, timezone_str)

    workspace = Workspace.objects.create(
        name=clean_name,
        timezone=clean_tz,
        owner_user=user,
    )

    Membership.objects.create(
        workspace=workspace,
        user=user,
        access_role=AccessRole.OWNER,
        employment_type=EmploymentType.IN_HOUSE,
        status=MembershipStatus.ACTIVE,
        ai_use_allowed=True,
    )

    return workspace


@transaction.atomic
def update_workspace_info(
    *,
    user: Any,
    workspace: Workspace,
    name: str,
    timezone_str: str,
) -> Workspace:
    """
    Cập nhật tên và timezone của workspace.
    Quy tắc an ninh Spec 3.1 & B01:
    - Chỉ Chủ (OWNER) được sửa thông tin workspace trong B01.
    - Thành viên không phải Chủ nhận HTTP 403 (PermissionDenied).
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    # Kiểm tra quyền Chủ workspace
    membership = get_active_membership(user, workspace)
    if not membership or not membership.is_active or membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa thông tin workspace.")

    if workspace.owner_user_id != user.id:
        raise PermissionDenied("Thông tin Chủ workspace không nhất quán.")

    clean_name, clean_tz = validate_workspace_input(name, timezone_str)

    workspace.name = clean_name
    workspace.timezone = clean_tz
    workspace.save(update_fields=["name", "timezone", "updated_at"])

    return workspace


def switch_active_workspace(request: Any, workspace_id: uuid.UUID | str) -> Workspace:
    """
    Chuyển workspace đang chọn trong phiên làm việc (session).
    Kiểm tra lại quyền truy cập backend: nếu không có membership ACTIVE, ném 404.
    """
    workspace, _ = get_workspace_for_user(request.user, workspace_id)
    request.session[ACTIVE_WORKSPACE_SESSION_KEY] = str(workspace.id)
    return workspace


def get_current_active_workspace(request: Any) -> tuple[Workspace | None, Membership | None]:
    """
    Lấy workspace đang chọn trong session hoặc workspace mặc định đầu tiên của user.
    QUAN TRỌNG:
    - Kiểm tra lại membership trên mỗi request; không coi session là bằng chứng quyền.
    - Nếu membership bị vô hiệu/xóa, session key lập tức bị xóa bỏ và chuyển sang fallback.
    """
    if not hasattr(request, "user") or not request.user.is_authenticated:
        return None, None

    active_id_str = request.session.get(ACTIVE_WORKSPACE_SESSION_KEY)
    if active_id_str:
        try:
            active_uuid = uuid.UUID(active_id_str)
            membership = (
                Membership.objects.filter(
                    user=request.user,
                    workspace_id=active_uuid,
                    status=MembershipStatus.ACTIVE,
                )
                .select_related("workspace")
                .first()
            )
            if membership:
                return membership.workspace, membership
            # Session lưu workspace không còn hợp lệ hoặc membership bị vô hiệu
            del request.session[ACTIVE_WORKSPACE_SESSION_KEY]
        except (ValueError, AttributeError, KeyError):
            request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)

    # Fallback: Lấy workspace active đầu tiên của user nếu có
    first_ws = get_user_workspaces(request.user).first()
    if first_ws:
        membership = get_active_membership(request.user, first_ws)
        if membership:
            request.session[ACTIVE_WORKSPACE_SESSION_KEY] = str(first_ws.id)
            return first_ws, membership

    return None, None
