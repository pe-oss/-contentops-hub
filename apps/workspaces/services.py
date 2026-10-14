import uuid
from urllib.parse import urlparse
from typing import Any
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    AccessRole, BrandProfile, ContentItem, ContentItemState, ContentVersion,
    ContentApproval, EmploymentType, Membership, MembershipStatus, Package, PackageStatus,
    PlanApproval, ReviewDecision, Task, TaskExecutionMode, TaskRole, TaskStatus,
    Workspace, validate_timezone,
)
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

import datetime
import hashlib
import logging
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import AccountEmailIdentity
from apps.accounts.services import normalize_email
from .models import Invitation, InvitationStatus

logger = logging.getLogger(__name__)
INVITATION_EXPIRE_DAYS = 7
INVITATION_RESEND_COOLDOWN_SECONDS = 60


def hash_invitation_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def send_invitation_email(
    invitation: Invitation,
    raw_token: str,
    request=None,
) -> None:
    """
    Gửi email thông báo lời mời sau khi transaction commit.
    Tuyệt đối không ghi raw token hay full invitation URL vào logs.
    """
    accept_path = reverse("workspaces:invitation_accept", kwargs={"token": raw_token})
    if request:
        accept_url = request.build_absolute_uri(accept_path)
    else:
        accept_url = f"http://localhost:8000{accept_path}"

    subject = f"Lời mời tham gia workspace {invitation.workspace.name} trên SaaS-Content"
    message = (
        f"Xin chào,\n\n"
        f"Bạn được mời tham gia workspace '{invitation.workspace.name}' với vai trò "
        f"{invitation.get_access_role_display()} ({invitation.get_employment_type_display()}).\n\n"
        f"Vui lòng truy cập đường dẫn sau để đăng nhập và chấp nhận lời mời (có hiệu lực trong {INVITATION_EXPIRE_DAYS} ngày):\n"
        f"{accept_url}\n\n"
        f"Nếu bạn không yêu cầu lời mời này, vui lòng bỏ qua email này.\n"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
        logger.info(
            "Đã gửi email lời mời workspace_id=%s tới email=%s (id=%s)",
            invitation.workspace_id,
            invitation.email,
            invitation.id,
        )
    except Exception as exc:
        logger.warning(
            "Lỗi gửi email lời mời workspace_id=%s tới email=%s: %s",
            invitation.workspace_id,
            invitation.email,
            exc,
        )


@transaction.atomic
def create_workspace_invitation(
    *,
    user: Any,
    workspace: Workspace,
    email: str,
    employment_type: str = EmploymentType.IN_HOUSE,
    ai_use_allowed: bool = False,
    request=None,
    send_email: bool = True,
) -> tuple[Invitation, str]:
    """
    Tạo lời mời tham gia workspace (chỉ Chủ mới có quyền).
    - Chuẩn hóa email theo AccountEmailIdentity.
    - Token an toàn sinh ngẫu nhiên, lưu hash SHA-256 trong CSDL.
    - Hết hạn sau 7 ngày.
    - Không cho mời vào vai trò OWNER.
    - Gửi email sau commit; lỗi gửi mail không hủy lời mời.
    - Trả về (invitation, raw_token) để Chủ có thể sao chép link trực tiếp.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    # 1. Kiểm tra quyền Chủ workspace
    membership = get_active_membership(user, workspace)
    if not membership or membership.access_role != AccessRole.OWNER or workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền tạo lời mời.")

    # 2. Chuẩn hóa email
    norm_email = normalize_email(email)
    if not norm_email or "@" not in norm_email:
        raise ValidationError({"email": "Địa chỉ email không hợp lệ."})

    # 3. Kiểm tra thành viên hiện tại trong workspace
    existing_membership = (
        Membership.objects.filter(
            workspace=workspace,
            user__email_identity__normalized_email=norm_email,
        )
        .select_related("user")
        .first()
    )
    if not existing_membership:
        existing_membership = (
            Membership.objects.filter(
                workspace=workspace,
                user__email__iexact=norm_email,
            )
            .select_related("user")
            .first()
        )

    if existing_membership:
        if existing_membership.status == MembershipStatus.ACTIVE:
            raise ValidationError({"email": "Người dùng với email này đã là thành viên đang hoạt động của workspace."})
        elif existing_membership.status == MembershipStatus.INACTIVE:
            raise ValidationError({
                "email": "Thành viên này đang bị vô hiệu hóa trong workspace. Hãy kích hoạt lại thay vì tạo lời mời mới."
            })

    # 4. Kiểm tra lời mời trùng đang chờ xử lý
    now = timezone.now()
    active_invitation = (
        Invitation.objects.filter(
            workspace=workspace,
            email=norm_email,
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .first()
    )
    if active_invitation:
        raise ValidationError({
            "email": "Đã có lời mời đang chờ xử lý gửi tới email này. Bạn có thể sao chép link hoặc gửi lại."
        })

    # 5. Sinh token và lưu trữ
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)
    expires_at = now + datetime.timedelta(days=INVITATION_EXPIRE_DAYS)

    invitation = Invitation.objects.create(
        workspace=workspace,
        email=norm_email,
        token_hash=token_hash,
        access_role=AccessRole.MEMBER,
        employment_type=employment_type,
        ai_use_allowed=ai_use_allowed,
        invited_by=user,
        expires_at=expires_at,
        last_sent_at=now,
    )

    # 6. Gửi email sau commit
    if send_email:
        transaction.on_commit(
            lambda: send_invitation_email(invitation, raw_token, request=request)
        )

    return invitation, raw_token


@transaction.atomic
def resend_workspace_invitation(
    *,
    user: Any,
    invitation: Invitation,
    request=None,
    send_email: bool = True,
) -> str:
    """
    Gửi lại lời mời (Chỉ Chủ).
    - Có cooldown 60 giây.
    - Sinh token mới, cập nhật expires_at thêm 7 ngày.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    if invitation.workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền gửi lại lời mời.")

    if invitation.accepted_at is not None:
        raise ValidationError("Lời mời này đã được chấp nhận, không thể gửi lại.")
    if invitation.revoked_at is not None:
        raise ValidationError("Lời mời này đã bị thu hồi, hãy tạo lời mời mới.")

    now = timezone.now()
    if invitation.last_sent_at:
        elapsed = (now - invitation.last_sent_at).total_seconds()
        if elapsed < INVITATION_RESEND_COOLDOWN_SECONDS:
            remaining = int(INVITATION_RESEND_COOLDOWN_SECONDS - elapsed)
            raise ValidationError(f"Vui lòng đợi {remaining} giây trước khi gửi lại lời mời.")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)
    expires_at = now + datetime.timedelta(days=INVITATION_EXPIRE_DAYS)

    invitation.token_hash = token_hash
    invitation.expires_at = expires_at
    invitation.last_sent_at = now
    invitation.save(update_fields=["token_hash", "expires_at", "last_sent_at", "updated_at"])

    if send_email:
        transaction.on_commit(
            lambda: send_invitation_email(invitation, raw_token, request=request)
        )

    return raw_token


@transaction.atomic
def revoke_workspace_invitation(
    *,
    user: Any,
    invitation: Invitation,
) -> Invitation:
    """
    Thu hồi lời mời (Chỉ Chủ).
    Sau khi thu hồi, người nhận không thể chấp nhận được nữa.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    if invitation.workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền thu hồi lời mời.")

    if invitation.accepted_at is not None:
        raise ValidationError("Lời mời này đã được chấp nhận, không thể thu hồi.")

    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])
    return invitation


@transaction.atomic
def accept_workspace_invitation(
    *,
    user: Any,
    raw_token: str,
) -> tuple[Workspace, Membership]:
    """
    Chấp nhận lời mời tham gia workspace.
    Yêu cầu:
    - User đã đăng nhập và đã xác minh email identity.
    - Email của user phải khớp với email được mời (sau chuẩn hóa).
    - Lời mời chưa bị thu hồi, chưa hết hạn và chưa được chấp nhận.
    - Dùng select_for_update() trên Invitation và Membership để chống race condition.
    - Cấp membership với vai trò MEMBER, gán employment_type và ai_use_allowed từ lời mời.
    - Không tin email/role từ client.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập để chấp nhận lời mời.")

    # 1. Kiểm tra xác minh email identity của user
    try:
        identity = user.email_identity
    except (AttributeError, AccountEmailIdentity.DoesNotExist):
        identity = None

    if not identity or not identity.is_verified:
        raise ValidationError("Tài khoản của bạn chưa xác minh email. Vui lòng xác minh email trước khi nhận lời mời.")

    # 2. Tìm và khóa bản ghi Invitation
    token_hash = hash_invitation_token(raw_token)
    invitation = (
        Invitation.objects.select_for_update()
        .filter(token_hash=token_hash)
        .select_related("workspace")
        .first()
    )
    if not invitation:
        raise ValidationError("Lời mời không tồn tại hoặc liên kết không hợp lệ.")

    # 3. Kiểm tra các điều kiện an toàn của Invitation
    if invitation.accepted_at is not None:
        raise ValidationError("Lời mời này đã được sử dụng trước đó.")
    if invitation.revoked_at is not None:
        raise ValidationError("Lời mời này đã bị thu hồi bởi Chủ workspace.")
    if invitation.expires_at <= timezone.now():
        raise ValidationError("Lời mời này đã hết hạn.")

    # 4. Kiểm tra khớp email
    user_email = normalize_email(identity.normalized_email)
    if user_email != invitation.email:
        raise ValidationError(
            f"Email đã xác minh của tài khoản ({user_email}) không khớp với email được mời ({invitation.email})."
        )

    # 5. Tạo hoặc kích hoạt Membership cho user
    workspace = invitation.workspace
    membership = (
        Membership.objects.select_for_update()
        .filter(workspace=workspace, user=user)
        .first()
    )
    if membership:
        membership.access_role = AccessRole.MEMBER
        membership.employment_type = invitation.employment_type
        membership.ai_use_allowed = invitation.ai_use_allowed
        membership.status = MembershipStatus.ACTIVE
        membership.save(update_fields=["access_role", "employment_type", "ai_use_allowed", "status", "updated_at"])
    else:
        membership = Membership.objects.create(
            workspace=workspace,
            user=user,
            access_role=AccessRole.MEMBER,
            employment_type=invitation.employment_type,
            ai_use_allowed=invitation.ai_use_allowed,
            status=MembershipStatus.ACTIVE,
        )

    # 6. Đánh dấu lời mời đã chấp nhận
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])

    return workspace, membership



@transaction.atomic
def update_member_settings(
    *,
    user: Any,
    workspace: Workspace,
    membership: Membership,
    employment_type: str,
    ai_use_allowed: bool,
) -> Membership:
    """
    Cập nhật cài đặt của thành viên (chỉ Chủ).
    Không cho phép can thiệp vào Chủ workspace.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    if workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa cài đặt thành viên.")

    if membership.workspace_id != workspace.id:
        raise ValidationError("Thành viên không thuộc workspace này.")

    # Bảo vệ Chủ: không đổi membership của Chủ qua hàm này
    if membership.user_id == workspace.owner_user_id or membership.access_role == AccessRole.OWNER:
        raise ValidationError("Không thể sửa vai trò hoặc loại quan hệ của Chủ workspace qua chức năng này.")

    if employment_type not in EmploymentType.values:
        raise ValidationError({"employment_type": "Loại hình quan hệ không hợp lệ."})

    membership.employment_type = employment_type
    membership.ai_use_allowed = bool(ai_use_allowed)
    membership.save(update_fields=["employment_type", "ai_use_allowed", "updated_at"])
    return membership


@transaction.atomic
def deactivate_membership(
    *,
    user: Any,
    workspace: Workspace,
    membership: Membership,
) -> Membership:
    """
    Vô hiệu hóa thành viên (status = INACTIVE). Chỉ Chủ.
    Bảo vệ Chủ: Tuyệt đối không cho phép vô hiệu hóa Chủ workspace.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    if workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền vô hiệu hóa thành viên.")

    if membership.workspace_id != workspace.id:
        raise ValidationError("Thành viên không thuộc workspace này.")

    if membership.user_id == workspace.owner_user_id or membership.access_role == AccessRole.OWNER:
        raise ValidationError("Không thể vô hiệu hóa Chủ workspace.")

    membership.status = MembershipStatus.INACTIVE
    membership.save(update_fields=["status", "updated_at"])
    return membership


@transaction.atomic
def reactivate_membership(
    *,
    user: Any,
    workspace: Workspace,
    membership: Membership,
) -> Membership:
    """
    Kích hoạt lại thành viên (status = ACTIVE). Chỉ Chủ.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    if workspace.owner_user_id != user.id:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền kích hoạt lại thành viên.")

    if membership.workspace_id != workspace.id:
        raise ValidationError("Thành viên không thuộc workspace này.")

    membership.status = MembershipStatus.ACTIVE
    membership.save(update_fields=["status", "updated_at"])
    return membership



class ConcurrencyConflictError(Exception):
    """Lỗi xung đột phiên bản dữ liệu đồng thời (Optimistic Concurrency Control, HTTP 409)."""
    pass


@transaction.atomic
def save_brand_profile(
    *,
    user: Any,
    workspace: Workspace,
    name: str,
    product_summary: str,
    target_audience: str,
    tone_of_voice: str = "",
    avoid_guidelines: str = "",
    allowed_claims: str = "",
    source_urls: list[str] | None = None,
    expected_revision: int | None = None,
) -> BrandProfile:
    """
    Tạo hoặc cập nhật hồ sơ thương hiệu cho Workspace theo Spec B03 (mục 3.1, 4, 9, 10, 14):
    - Chỉ Chủ workspace (OWNER) có quyền tạo hoặc sửa.
    - Thành viên ném PermissionDenied (HTTP 403).
    - Người ngoài không có quyền ném PermissionDenied hoặc Http404 (ở tầng view).
    - Hỗ trợ Optimistic Concurrency Control: nếu expected_revision được truyền vào và
      không khớp với revision hiện tại trong CSDL, ném ConcurrencyConflictError (HTTP 409).
    - Mỗi lần cập nhật thành công, revision tự động tăng thêm 1.
    - Ghi nhận updated_by = user.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    # 1. Kiểm tra quyền Chủ workspace
    membership = get_active_membership(user, workspace)
    if not membership or not membership.is_active or membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền cập nhật hồ sơ thương hiệu.")

    if workspace.owner_user_id != user.id:
        raise PermissionDenied("Thông tin Chủ workspace không nhất quán.")

    # 2. Khóa dòng Workspace để tuần tự hóa thao tác (kể cả khi BrandProfile chưa tồn tại)
    Workspace.objects.select_for_update().filter(id=workspace.id).first()

    # Khóa dòng BrandProfile để đảm bảo tính tuần tự
    brand_profile = (
        BrandProfile.objects.select_for_update()
        .filter(workspace=workspace)
        .first()
    )

    clean_urls = list(source_urls or [])

    if brand_profile:
        # Kiểm tra xung đột phiên bản
        if expected_revision is not None and brand_profile.revision != expected_revision:
            raise ConcurrencyConflictError(
                f"Hồ sơ thương hiệu đã bị sửa đổi ở phiên khác (phiên bản hiện tại: {brand_profile.revision}, phiên bản của bạn: {expected_revision}). Vui lòng kiểm tra lại để tránh ghi đè dữ liệu."
            )

        brand_profile.name = name
        brand_profile.product_summary = product_summary
        brand_profile.target_audience = target_audience
        brand_profile.tone_of_voice = tone_of_voice or ""
        brand_profile.avoid_guidelines = avoid_guidelines or ""
        brand_profile.allowed_claims = allowed_claims or ""
        brand_profile.source_urls = clean_urls
        brand_profile.revision += 1
        brand_profile.updated_by = user
        brand_profile.full_clean()
        brand_profile.save()
        return brand_profile
    else:
        # Trường hợp tạo mới
        if expected_revision is not None and expected_revision > 0:
            raise ConcurrencyConflictError(
                f"Hồ sơ thương hiệu chưa tồn tại nhưng yêu cầu phiên bản {expected_revision}."
            )

        brand_profile = BrandProfile(
            workspace=workspace,
            name=name,
            product_summary=product_summary,
            target_audience=target_audience,
            tone_of_voice=tone_of_voice or "",
            avoid_guidelines=avoid_guidelines or "",
            allowed_claims=allowed_claims or "",
            source_urls=clean_urls,
            revision=1,
            updated_by=user,
        )
        brand_profile.full_clean()
        try:
            with transaction.atomic():
                brand_profile.save()
        except IntegrityError:
            raise ConcurrencyConflictError(
                "Hồ sơ thương hiệu đã được tạo ở một phiên khác. Vui lòng tải lại trang."
            )
        return brand_profile

from .models import (
    ContentItem,
    ContentItemState,
    Package,
    PackageStatus,
    PlanApproval,
    Task,
    TaskRole,
    TaskStatus,
)


@transaction.atomic
def create_package(
    *,
    user: Any,
    workspace: Workspace,
    name: str,
    objective: str,
    coordinator_membership: Membership,
    start_date: Any,
    end_date: Any,
    channel: str = "FACEBOOK",
) -> Package:
    """
    Tạo gói nội dung (Spec F02, B04):
    - Chủ workspace có quyền tạo gói và chỉ định người điều phối.
    - Người điều phối phải thuộc cùng workspace và đang hoạt động (ACTIVE).
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    user_membership = get_active_membership(user, workspace)
    if not user_membership or not user_membership.is_active or user_membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền tạo Gói nội dung.")

    if coordinator_membership.workspace_id != workspace.id:
        raise ValidationError({"coordinator_membership": "Thành viên điều phối phải thuộc cùng workspace."})
    if not coordinator_membership.is_active:
        raise ValidationError({"coordinator_membership": "Thành viên điều phối phải đang hoạt động (ACTIVE)."})

    package = Package(
        workspace=workspace,
        name=name,
        objective=objective,
        coordinator_membership=coordinator_membership,
        start_date=start_date,
        end_date=end_date,
        channel=channel or "FACEBOOK",
        status=PackageStatus.DRAFT,
        plan_revision=1,
        row_version=1,
    )
    package.full_clean()
    package.save()
    return package


@transaction.atomic
def update_package(
    *,
    user: Any,
    package: Package,
    name: str,
    objective: str,
    coordinator_membership: Membership,
    start_date: Any,
    end_date: Any,
    expected_row_version: int | None = None,
) -> Package:
    """
    Chỉnh sửa thông tin gói nội dung.
    - Sau khi duyệt (ACTIVE): Chỉ Chủ mới sửa được phạm vi/lịch và tăng plan_revision (Spec F02).
    - Hỗ trợ Optimistic Concurrency Control qua row_version.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    user_membership = get_active_membership(user, package.workspace)
    if not user_membership or not user_membership.is_active or user_membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền sửa thông tin Gói nội dung.")

    # Khóa dòng package
    locked_pkg = Package.objects.select_for_update().filter(id=package.id).first()
    if not locked_pkg:
        raise ValidationError("Gói nội dung không tồn tại.")

    if expected_row_version is not None and locked_pkg.row_version != expected_row_version:
        raise ConcurrencyConflictError(
            f"Gói nội dung đã bị thay đổi ở một phiên khác (phiên bản hiện tại: {locked_pkg.row_version}, của bạn: {expected_row_version})."
        )

    if coordinator_membership.workspace_id != locked_pkg.workspace_id:
        raise ValidationError({"coordinator_membership": "Thành viên điều phối phải thuộc cùng workspace."})
    if not coordinator_membership.is_active:
        raise ValidationError({"coordinator_membership": "Thành viên điều phối phải đang hoạt động (ACTIVE)."})

    locked_pkg.name = name
    locked_pkg.objective = objective
    locked_pkg.coordinator_membership = coordinator_membership
    locked_pkg.start_date = start_date
    locked_pkg.end_date = end_date
    locked_pkg.row_version += 1
    if locked_pkg.status == PackageStatus.ACTIVE:
        locked_pkg.plan_revision += 1

    locked_pkg.full_clean()
    locked_pkg.save()
    return locked_pkg
@transaction.atomic
def add_content_item(
    *,
    user: Any,
    package: Package,
    title: str,
    brief: str,
    cta: str,
    writing_deadline: Any,
    editing_deadline: Any,
    review_deadline: Any,
    planned_publish_at: Any,
    writer_membership: Membership,
    editor_membership: Membership,
    publisher_membership: Membership,
) -> ContentItem:
    """
    Thêm bài viết vào kế hoạch (Spec F02, B04):
    - Chủ hoặc Người điều phối gói có quyền thêm bài.
    - Giới hạn: tối đa 50 bài / gói (Spec mục 4).
    - 3 vai trò phân công phải thuộc cùng workspace và đang hoạt động (ACTIVE).
    - Trật tự deadline: viết <= biên tập <= duyệt <= đăng.
    - Lịch bài phải nằm trong khoảng thời gian của gói.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    user_membership = get_active_membership(user, package.workspace)
    if not user_membership or not user_membership.is_active:
        raise PermissionDenied("Bạn không có quyền trong workspace này.")

    # Phân quyền: Chủ workspace hoặc người điều phối gói (Spec F02)
    is_owner = user_membership.access_role == AccessRole.OWNER
    is_coordinator = package.coordinator_membership_id == user_membership.id
    if not is_owner and not is_coordinator:
        raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền thêm bài vào kế hoạch.")

    # Khóa package
    locked_pkg = Package.objects.select_for_update().filter(id=package.id).first()
    if not locked_pkg:
        raise ValidationError("Gói nội dung không tồn tại.")

    current_item_count = ContentItem.objects.filter(package=locked_pkg).count()
    if current_item_count >= 50:
        raise ValidationError({"title": "Một gói nội dung tối đa 50 bài viết theo Spec R1."})

    # Kiểm tra phân công cùng workspace & ACTIVE
    for role_name, member in [
        ("writer_membership", writer_membership),
        ("editor_membership", editor_membership),
        ("publisher_membership", publisher_membership),
    ]:
        if member.workspace_id != locked_pkg.workspace_id:
            raise ValidationError({role_name: "Thành viên được phân công phải thuộc cùng workspace."})
        if not member.is_active:
            raise ValidationError({role_name: "Thành viên được phân công phải đang hoạt động (ACTIVE)."})

    item = ContentItem(
        workspace=locked_pkg.workspace,
        package=locked_pkg,
        title=title,
        brief=brief,
        cta=cta or "",
        writing_deadline=writing_deadline,
        editing_deadline=editing_deadline,
        review_deadline=review_deadline,
        planned_publish_at=planned_publish_at,
        writer_membership=writer_membership,
        editor_membership=editor_membership,
        publisher_membership=publisher_membership,
        state=ContentItemState.TODO,
        row_version=1,
        order=current_item_count + 1,
    )
    item.full_clean()
    item.save()
    return item
@transaction.atomic
def update_content_item(
    *,
    user: Any,
    item: ContentItem,
    title: str,
    brief: str,
    cta: str,
    writing_deadline: Any,
    editing_deadline: Any,
    review_deadline: Any,
    planned_publish_at: Any,
    writer_membership: Membership,
    editor_membership: Membership,
    publisher_membership: Membership,
    expected_row_version: int | None = None,
) -> ContentItem:
    """
    Sửa bài viết trong kế hoạch.
    - Khi kế hoạch đã duyệt: chỉ Chủ mới có quyền sửa (Spec F02).
    - Hỗ trợ Optimistic Concurrency Control qua row_version.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    user_membership = get_active_membership(user, item.workspace)
    if not user_membership or not user_membership.is_active:
        raise PermissionDenied("Bạn không có quyền trong workspace này.")

    package = item.package
    is_owner = user_membership.access_role == AccessRole.OWNER
    is_coordinator = package.coordinator_membership_id == user_membership.id

    if package.status == PackageStatus.ACTIVE:
        if not is_owner:
            raise PermissionDenied("Khi kế hoạch đã duyệt, chỉ Chủ workspace mới có quyền sửa bài viết.")
    else:
        if not is_owner and not is_coordinator:
            raise PermissionDenied("Chỉ Chủ workspace hoặc Người điều phối mới có quyền sửa bài viết.")

    locked_item = ContentItem.objects.select_for_update().filter(id=item.id).first()
    if not locked_item:
        raise ValidationError("Bài viết không tồn tại.")

    if expected_row_version is not None and locked_item.row_version != expected_row_version:
        raise ConcurrencyConflictError(
            f"Bài viết đã bị thay đổi ở một phiên khác (phiên bản hiện tại: {locked_item.row_version}, của bạn: {expected_row_version})."
        )

    for role_name, member in [
        ("writer_membership", writer_membership),
        ("editor_membership", editor_membership),
        ("publisher_membership", publisher_membership),
    ]:
        if member.workspace_id != locked_item.workspace_id:
            raise ValidationError({role_name: "Thành viên được phân công phải thuộc cùng workspace."})
        if not member.is_active:
            raise ValidationError({role_name: "Thành viên được phân công phải đang hoạt động (ACTIVE)."})

    locked_item.title = title
    locked_item.brief = brief
    locked_item.cta = cta or ""
    locked_item.writing_deadline = writing_deadline
    locked_item.editing_deadline = editing_deadline
    locked_item.review_deadline = review_deadline
    locked_item.planned_publish_at = planned_publish_at
    locked_item.writer_membership = writer_membership
    locked_item.editor_membership = editor_membership
    locked_item.publisher_membership = publisher_membership
    locked_item.row_version += 1

    locked_item.full_clean()
    locked_item.save()

    if package.status == PackageStatus.ACTIVE:
        package.plan_revision += 1
        package.save(update_fields=["plan_revision"])

        Task.objects.filter(item=locked_item, role=TaskRole.WRITE).update(
            assignee_membership=writer_membership,
            due_at=writing_deadline,
        )
        Task.objects.filter(item=locked_item, role=TaskRole.EDIT).update(
            assignee_membership=editor_membership,
            due_at=editing_deadline,
        )
        Task.objects.filter(item=locked_item, role=TaskRole.PUBLISH).update(
            assignee_membership=publisher_membership,
            due_at=planned_publish_at,
        )
def _build_plan_snapshot(package: Package, items: list[ContentItem], brand_snap: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": str(package.id),
        "package_name": package.name,
        "objective": package.objective,
        "channel": package.channel,
        "start_date": package.start_date.isoformat() if package.start_date else None,
        "end_date": package.end_date.isoformat() if package.end_date else None,
        "plan_revision": package.plan_revision,
        "brand_snapshot": brand_snap,
        "items": [
            {
                "item_id": str(it.id),
                "title": it.title,
                "brief": it.brief,
                "cta": it.cta,
                "writing_deadline": it.writing_deadline.isoformat() if it.writing_deadline else None,
                "editing_deadline": it.editing_deadline.isoformat() if it.editing_deadline else None,
                "review_deadline": it.review_deadline.isoformat() if it.review_deadline else None,
                "planned_publish_at": it.planned_publish_at.isoformat() if it.planned_publish_at else None,
                "writer_id": str(it.writer_membership.user_id),
                "editor_id": str(it.editor_membership.user_id),
                "publisher_id": str(it.publisher_membership.user_id),
            }
            for it in items
        ],
    }


@transaction.atomic
def approve_plan(
    *,
    user: Any,
    package: Package,
    idempotency_key: str = "",
) -> tuple[Package, PlanApproval, list[Task]]:
    """
    Chủ duyệt kế hoạch gói nội dung (Spec F02, AC04, AC05, B04).
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")

    user_membership = get_active_membership(user, package.workspace)
    if not user_membership or not user_membership.is_active or user_membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền phê duyệt kế hoạch.")

    locked_pkg = (
        Package.objects.select_for_update()
        .filter(id=package.id)
        .select_related("workspace", "coordinator_membership")
        .first()
    )
    if not locked_pkg:
        raise ValidationError("Gói nội dung không tồn tại.")

    clean_idempotency_key = (idempotency_key or "").strip()
    if clean_idempotency_key:
        existing_approval = PlanApproval.objects.filter(
            package=locked_pkg,
            idempotency_key=clean_idempotency_key,
        ).first()
        if existing_approval:
            existing_tasks = list(Task.objects.filter(item__package=locked_pkg))
            return locked_pkg, existing_approval, existing_tasks

    if locked_pkg.status != PackageStatus.DRAFT:
        raise ValidationError(f"Chỉ có thể duyệt kế hoạch khi ở trạng thái nháp (DRAFT). Hiện tại: {locked_pkg.status}.")

    items = list(
        ContentItem.objects.select_for_update()
        .filter(package=locked_pkg)
        .select_related("writer_membership", "editor_membership", "publisher_membership")
    )
    if not items:
        raise ValidationError("Kế hoạch phải có ít nhất 1 bài viết để có thể phê duyệt.")

    for item in items:
        item.full_clean()
        for role_name, member in [
            ("writer_membership", item.writer_membership),
            ("editor_membership", item.editor_membership),
            ("publisher_membership", item.publisher_membership),
        ]:
            if not member or not member.is_active or member.workspace_id != locked_pkg.workspace_id:
                raise ValidationError(
                    f"Bài '{item.title}' có người thực hiện ({role_name}) không hợp lệ hoặc không còn hoạt động."
                )

    brand_profile = BrandProfile.objects.filter(workspace=locked_pkg.workspace).first()
    brand_snap = brand_profile.to_snapshot() if brand_profile else {
        "brand_profile_id": None,
        "brand_name": locked_pkg.workspace.name,
        "product_summary": "",
        "target_audience": "",
        "revision": 0,
        "source_urls": [],
    }

    plan_snapshot = _build_plan_snapshot(locked_pkg, items, brand_snap)

    locked_pkg.brand_snapshot = brand_snap
    locked_pkg.status = PackageStatus.ACTIVE
    locked_pkg.row_version += 1
    locked_pkg.save(update_fields=["brand_snapshot", "status", "row_version", "updated_at"])

    approval = PlanApproval.objects.create(
        package=locked_pkg,
        plan_revision=locked_pkg.plan_revision,
        immutable_plan_snapshot=plan_snapshot,
        owner=user,
        idempotency_key=clean_idempotency_key,
    )

    created_tasks = []
    for item in items:
        for role, defaults in [
            (TaskRole.WRITE, {"workspace": locked_pkg.workspace, "assignee_membership": item.writer_membership, "due_at": item.writing_deadline, "status": TaskStatus.READY}),
            (TaskRole.EDIT, {"workspace": locked_pkg.workspace, "assignee_membership": item.editor_membership, "due_at": item.editing_deadline, "status": TaskStatus.WAITING}),
            (TaskRole.PUBLISH, {"workspace": locked_pkg.workspace, "assignee_membership": item.publisher_membership, "due_at": item.planned_publish_at, "status": TaskStatus.WAITING}),
        ]:
            t, _ = Task.objects.get_or_create(item=item, role=role, defaults=defaults)
            created_tasks.append(t)

    return locked_pkg, approval, created_tasks
def validate_https_urls(urls: list[str] | None) -> list[str]:
    """
    Kiểm tra và chuẩn hóa danh sách URLs tham khảo theo Spec mục 4, 9:
    - Bắt buộc giao thức HTTPS hợp lệ.
    - Chặn các scheme khác (http, javascript, file, v.v.).
    """
    if not urls:
        return []
    cleaned: list[str] = []
    for u in urls:
        if not u or not isinstance(u, str):
            continue
        clean_u = u.strip()
        if not clean_u:
            continue
        parsed = urlparse(clean_u)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValidationError(f"URL tham khảo phải là HTTPS hợp lệ: '{clean_u}'")
        cleaned.append(clean_u)
    return cleaned


def format_brief_for_copy(item: ContentItem) -> str:
    """
    Tạo nội dung Brief định dạng chuẩn để sao chép sang AI riêng (Spec F03, B05).
    Bao gồm mục tiêu, đối tượng, giọng văn, yêu cầu bài, điều tránh, định dạng đầu ra
    và yêu cầu đánh dấu thông tin chưa biết.
    """
    pkg = item.package
    brand_snap = pkg.brand_snapshot or {}
    brand_name = brand_snap.get("brand_name") or pkg.workspace.name
    target_audience = brand_snap.get("target_audience") or "Chưa chỉ định cụ thể"
    positioning = brand_snap.get("positioning") or ""
    tone_of_voice = brand_snap.get("tone_of_voice") or ""
    rules_to_avoid = brand_snap.get("rules_to_avoid") or "Không có điều cấm cụ thể"
    mandatory_info = brand_snap.get("mandatory_info") or "Không có thông tin bắt buộc"

    voice_str = f"{positioning} | {tone_of_voice}".strip(" |") or "Chuyên nghiệp, rõ ràng, phù hợp thương hiệu"

    lines = [
        f"=== BRIEF NỘI DUNG: {item.title} ===",
        f"Kênh đăng: {pkg.channel}",
        f"Mục tiêu chiến dịch: {pkg.objective}",
        "",
        "--- THÔNG TIN THƯƠNG HIỆU & ĐỊNH HƯỚNG ---",
        f"Thương hiệu: {brand_name}",
        f"Khách hàng mục tiêu: {target_audience}",
        f"Định vị & Giọng văn: {voice_str}",
        f"Điều tránh / Nguyên tắc cấm kỵ: {rules_to_avoid}",
        f"Thông tin bắt buộc phải có: {mandatory_info}",
        "",
        "--- YÊU CẦU BÀI VIẾT ---",
        f"Tiêu đề dự kiến: {item.title}",
        f"Yêu cầu nội dung (Brief): {item.brief}",
        f"Kêu gọi hành động (CTA): {item.cta or 'Tùy chọn phù hợp nội dung'}",
        f"Hạn hoàn thành: {item.writing_deadline.strftime('%H:%M ngày %d/%m/%Y') if item.writing_deadline else 'N/A'}",
        "",
        "--- NGUYÊN TẮC ĐẦU RA (AI PROMPT INSTRUCTION) ---",
        "1. Tạo bài viết hoàn chỉnh sẵn sàng đăng tải theo đúng định dạng kênh.",
        "2. Tuân thủ tuyệt đối các điều cần tránh và thông tin bắt buộc của thương hiệu.",
        "3. Nếu có dữ kiện hoặc số liệu chưa được cung cấp trong Brief, BẮT BUỘC đánh dấu bằng [CẦN XÁC MINH], tuyệt đối KHÔNG tự bịa đặt thông tin.",
    ]
    return "\n".join(lines)


def _check_writer_access(user: Any, item: ContentItem) -> Membership:
    """Kiểm tra quyền viết: người viết được phân công hoặc Chủ workspace (ACTIVE membership)."""
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")
    user_membership = get_active_membership(user, item.workspace)
    if not user_membership or not user_membership.is_active:
        raise PermissionDenied("Không có quyền truy cập.")
    if user_membership.access_role != AccessRole.OWNER and item.writer_membership_id != user_membership.id:
        raise PermissionDenied("Chỉ người viết được phân công hoặc Chủ workspace mới có quyền thực hiện thao tác này.")
    return user_membership


def _check_editor_access(user: Any, item: ContentItem) -> Membership:
    """Kiểm tra quyền biên tập: người biên tập được phân công hoặc Chủ workspace (ACTIVE membership)."""
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")
    user_membership = get_active_membership(user, item.workspace)
    if not user_membership or not user_membership.is_active:
        raise PermissionDenied("Không có quyền truy cập.")
    if user_membership.access_role != AccessRole.OWNER and item.editor_membership_id != user_membership.id:
        raise PermissionDenied("Chỉ người biên tập được phân công hoặc Chủ workspace mới có quyền thực hiện thao tác này.")
    return user_membership


def _check_owner_access(user: Any, item: ContentItem) -> Membership:
    """Kiểm tra quyền Chủ workspace (ACTIVE membership)."""
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")
    user_membership = get_active_membership(user, item.workspace)
    if not user_membership or not user_membership.is_active:
        raise PermissionDenied("Không có quyền truy cập.")
    if user_membership.access_role != AccessRole.OWNER:
        raise PermissionDenied("Chỉ Chủ workspace mới có quyền thực hiện thao tác này.")
    return user_membership


def _verify_row_version(current_version: int, expected_row_version: Any) -> None:
    """Kiểm tra phiên bản dòng (Optimistic Concurrency Control - AC10)."""
    if expected_row_version is not None and str(expected_row_version).strip() != "":
        try:
            exp_int = int(expected_row_version)
        except (ValueError, TypeError):
            exp_int = None
        if exp_int is not None and exp_int != current_version:
            raise ConcurrencyConflictError(
                f"Dữ liệu bài viết đã bị thay đổi bởi người khác (phiên bản hiện tại: {current_version}, bạn đang sửa trên phiên bản: {exp_int}). Vui lòng tải lại trang."
            )


@transaction.atomic
def start_writing_task(
    *,
    user: Any,
    item: ContentItem,
) -> Task:
    """
    Bắt đầu làm nhiệm vụ viết bài (Spec 6.1: TODO -> WRITING; Task WRITE: READY -> IN_PROGRESS).
    """
    _check_writer_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state == ContentItemState.TODO:
        locked_item.state = ContentItemState.WRITING
        locked_item.row_version += 1
        locked_item.save(update_fields=["state", "row_version", "updated_at"])

    write_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.WRITE).first()
    if write_task and write_task.status == TaskStatus.READY:
        write_task.status = TaskStatus.IN_PROGRESS
        write_task.save(update_fields=["status", "updated_at"])

    return write_task


@transaction.atomic
def save_draft_content(
    *,
    user: Any,
    item: ContentItem,
    text: str,
    reference_urls: list[str] | None = None,
    expected_row_version: Any = None,
) -> ContentItem:
    """
    Lưu bản nháp bài viết (Spec F03, 6.1, AC12):
    - Không tạo ContentVersion mới; chỉ lưu vào ContentItem.draft_text.
    - Cho phép lưu ngay cả khi bài bị BLOCKED (AC12).
    - Kiểm tra optimistic concurrency (AC10).
    - Tự động chuyển TODO -> WRITING nếu mới bắt đầu.
    """
    _check_writer_access(user, item)

    clean_urls = validate_https_urls(reference_urls)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    _verify_row_version(locked_item.row_version, expected_row_version)

    locked_item.draft_text = text or ""
    locked_item.draft_reference_urls = clean_urls

    if locked_item.state == ContentItemState.TODO:
        locked_item.state = ContentItemState.WRITING
        write_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.WRITE).first()
        if write_task and write_task.status == TaskStatus.READY:
            write_task.status = TaskStatus.IN_PROGRESS
            write_task.save(update_fields=["status", "updated_at"])

    locked_item.row_version += 1
    locked_item.save(update_fields=["draft_text", "draft_reference_urls", "state", "row_version", "updated_at"])
    return locked_item


@transaction.atomic
def submit_content_version(
    *,
    user: Any,
    item: ContentItem,
    text: str,
    reference_urls: list[str] | None = None,
    source: str = TaskExecutionMode.MANUAL,
    expected_row_version: Any = None,
    idempotency_key: str = "",
) -> tuple[ContentVersion, ContentItem]:
    """
    Người viết nộp phiên bản hoàn thành cho Biên tập (Spec F03, 6.1, AC06, AC08, AC10, AC12, B05):
    - Chặn nộp nếu bài bị BLOCKED (AC12).
    - Chặn nộp nếu trạng thái không hợp lệ (AC08).
    - Bắt buộc có nội dung văn bản.
    - Tạo ContentVersion bất biến với version_no tăng tuần tự.
    - Chuyển trạng thái bài: WRITING -> EDITING.
    - Cập nhật Tasks: Task WRITE -> DONE; Task EDIT -> READY.
    - Hỗ trợ chống double-click qua idempotency_key.
    """
    author_membership = _check_writer_access(user, item)

    clean_text = (text or "").strip()
    if not clean_text:
        raise ValidationError({"text": "Nội dung bài viết không được để trống khi nộp biên tập."})

    clean_urls = validate_https_urls(reference_urls)
    clean_idemp = (idempotency_key or "").strip()

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    if clean_idemp:
        existing_ver = ContentVersion.objects.filter(item=locked_item, idempotency_key=clean_idemp).first()
        if existing_ver:
            return existing_ver, locked_item

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'. Cần giải quyết chặn trước khi nộp bài.")

    if locked_item.state not in (ContentItemState.TODO, ContentItemState.WRITING):
        raise ValidationError(f"Không thể nộp bài viết ở trạng thái '{locked_item.get_state_display()}'. Chỉ chấp nhận nộp từ trạng thái Viết bài.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    last_ver = ContentVersion.objects.filter(item=locked_item).order_by("-version_no").first()
    next_no = (last_ver.version_no + 1) if last_ver else 1
    parent_ver = locked_item.latest_version

    version = ContentVersion.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version_no=next_no,
        text=clean_text,
        reference_urls=clean_urls,
        source=source if source in TaskExecutionMode.values else TaskExecutionMode.MANUAL,
        author_membership=author_membership,
        parent_version=parent_ver,
        idempotency_key=clean_idemp,
    )

    locked_item.latest_version_id = version.id
    locked_item.state = ContentItemState.EDITING
    locked_item.draft_text = ""
    locked_item.draft_reference_urls = []
    locked_item.row_version += 1
    locked_item.save(update_fields=["latest_version_id", "state", "draft_text", "draft_reference_urls", "row_version", "updated_at"])

    # Cập nhật trạng thái các Tasks (Spec 6.2)
    write_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.WRITE).first()
    if write_task:
        write_task.status = TaskStatus.DONE
        write_task.save(update_fields=["status", "updated_at"])

    edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
    if edit_task:
        edit_task.status = TaskStatus.READY
        edit_task.save(update_fields=["status", "updated_at"])

    return version, locked_item


@transaction.atomic
def create_editor_version(
    *,
    user: Any,
    item: ContentItem,
    text: str,
    reference_urls: list[str] | None = None,
    expected_row_version: Any = None,
) -> tuple[ContentVersion, ContentItem]:
    """
    Người biên tập tạo một phiên bản chỉnh sửa mới (Spec F04, AC06, B05).
    Không ghi đè phiên bản cũ; version_no tăng tuần tự.
    """
    editor_membership = _check_editor_access(user, item)

    clean_text = (text or "").strip()
    if not clean_text:
        raise ValidationError({"text": "Nội dung phiên bản chỉnh sửa không được để trống."})

    clean_urls = validate_https_urls(reference_urls)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.EDITING:
        raise ValidationError(f"Chỉ có thể tạo phiên bản chỉnh sửa khi bài đang ở trạng thái Biên tập. Hiện tại: '{locked_item.get_state_display()}'.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    last_ver = ContentVersion.objects.filter(item=locked_item).order_by("-version_no").first()
    next_no = (last_ver.version_no + 1) if last_ver else 1
    parent_ver = locked_item.latest_version

    version = ContentVersion.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version_no=next_no,
        text=clean_text,
        reference_urls=clean_urls,
        source=TaskExecutionMode.MANUAL,
        author_membership=editor_membership,
        parent_version=parent_ver,
    )

    locked_item.latest_version_id = version.id
    locked_item.row_version += 1
    locked_item.save(update_fields=["latest_version_id", "row_version", "updated_at"])

    return version, locked_item


@transaction.atomic
def request_changes_decision(
    *,
    user: Any,
    item: ContentItem,
    reason: str,
    expected_row_version: Any = None,
) -> tuple[ReviewDecision, ContentItem]:
    """
    Biên tập viên yêu cầu người viết sửa lại bài (Spec F04, 6.1, 6.2, AC06):
    - Bắt buộc có lý do sửa (reason).
    - Chuyển trạng thái: EDITING -> WRITING.
    - Task WRITE: mở lại (IN_PROGRESS); Task EDIT: quay về WAITING.
    - Lưu ReviewDecision append-only.
    """
    actor_membership = _check_editor_access(user, item)

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError({"reason": "Lý do yêu cầu sửa là bắt buộc."})

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.EDITING:
        raise ValidationError(f"Chỉ có thể yêu cầu sửa khi bài đang ở trạng thái Biên tập. Hiện tại: '{locked_item.get_state_display()}'.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="REQUEST_CHANGES",
        return_stage="WRITING",
        reason=clean_reason,
        actor_membership=actor_membership,
    )

    locked_item.state = ContentItemState.WRITING
    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "row_version", "updated_at"])

    # Cập nhật Tasks (Spec 6.2)
    write_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.WRITE).first()
    if write_task:
        write_task.status = TaskStatus.IN_PROGRESS
        write_task.save(update_fields=["status", "updated_at"])

    edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
    if edit_task:
        edit_task.status = TaskStatus.WAITING
        edit_task.save(update_fields=["status", "updated_at"])

    return decision, locked_item


def _sync_package_status(package_id: uuid.UUID) -> Package:
    """
    Cập nhật trạng thái của Gói nội dung theo Spec 6.2:
    - ACTIVE tự thành COMPLETED khi có ít nhất một bài không hủy và tất cả bài không hủy đã PUBLISHED.
    - Mở lại bài làm gói COMPLETED trở lại ACTIVE.
    - Lưu ý: Chỉ áp dụng khi gói đang ACTIVE hoặc COMPLETED.
    """
    locked_pkg = Package.objects.select_for_update().get(id=package_id)
    if locked_pkg.status not in (PackageStatus.ACTIVE, PackageStatus.COMPLETED):
        return locked_pkg

    items = ContentItem.objects.filter(package=locked_pkg)
    non_cancelled = items.exclude(state=ContentItemState.CANCELLED)
    non_cancelled_count = non_cancelled.count()

    if non_cancelled_count > 0:
        all_published = all(it.state == ContentItemState.PUBLISHED for it in non_cancelled)
        if all_published:
            if locked_pkg.status != PackageStatus.COMPLETED:
                locked_pkg.status = PackageStatus.COMPLETED
                locked_pkg.row_version += 1
                locked_pkg.save(update_fields=["status", "row_version", "updated_at"])
        else:
            if locked_pkg.status == PackageStatus.COMPLETED:
                locked_pkg.status = PackageStatus.ACTIVE
                locked_pkg.row_version += 1
                locked_pkg.save(update_fields=["status", "row_version", "updated_at"])
    return locked_pkg


@transaction.atomic
def owner_approve_item(
    *,
    user: Any,
    item: ContentItem,
    expected_version_id: uuid.UUID | str | None = None,
    expected_row_version: Any = None,
    idempotency_key: str | None = None,
) -> tuple[ContentApproval, ContentItem]:
    """
    Chủ workspace phê duyệt bài viết (Spec F05, 6.1, 6.3, AC07, AC10, AC12, B06):
    - Chỉ Chủ workspace mới có quyền phê duyệt (AccessRole.OWNER, ACTIVE membership).
    - Bài viết phải ở trạng thái OWNER_REVIEW.
    - Bài viết không được ở trạng thái BLOCKED (AC12).
    - Phiên bản được xem xét (expected_version_id) phải khớp với latest_version_id của bài viết (AC07).
      Nếu màn hình client xem v1 mà bài đã chuyển sang v2 hoặc version khác -> Bị từ chối ConcurrencyConflictError (HTTP 409).
    - Kiểm tra Optimistic Concurrency Control (AC10) trên row_version của bài.
    - Chống nhấp đôi qua idempotency_key (AC05/B06).
    - Vô hiệu hóa bất kỳ phê duyệt cũ nào còn hiệu lực trước đó (Spec 9).
    - Tạo bản ghi ContentApproval trỏ version_id đã chốt, approved_by, approved_at.
    - Chuyển trạng thái ContentItem: OWNER_REVIEW -> READY_TO_PUBLISH, lưu approval_id.
    - Cập nhật Task PUBLISH: chuyển trạng thái sang READY (mở việc xuất bản - Spec 6.2).
    - Ghi lịch sử ReviewDecision với decision="APPROVE".
    """
    _check_owner_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    clean_idemp = (idempotency_key or "").strip()
    if clean_idemp:
        existing_approval = ContentApproval.objects.filter(
            item=locked_item, idempotency_key=clean_idemp
        ).first()
        if existing_approval:
            return existing_approval, locked_item

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.OWNER_REVIEW:
        raise ValidationError(
            f"Chỉ có thể phê duyệt khi bài viết đang ở trạng thái Chờ Chủ duyệt (OWNER_REVIEW). Trạng thái hiện tại: '{locked_item.get_state_display()}'."
        )

    if not locked_item.latest_version_id:
        raise ValidationError("Bài viết chưa có phiên bản nội dung nào để phê duyệt.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    # AC07: Client đang xem phiên bản nào? Nếu client gửi expected_version_id mà không khớp latest_version_id -> ConcurrencyConflictError (409)
    if expected_version_id:
        try:
            if isinstance(expected_version_id, str):
                exp_ver_uuid = uuid.UUID(expected_version_id)
            else:
                exp_ver_uuid = expected_version_id
        except (ValueError, TypeError):
            exp_ver_uuid = None

        if exp_ver_uuid and exp_ver_uuid != locked_item.latest_version_id:
            raise ConcurrencyConflictError(
                "Phiên bản nội dung đang xem đã cũ và không phải phiên bản hiện hành mới nhất. Vui lòng tải lại trang để xem xét phiên bản mới nhất."
            )

    target_version = ContentVersion.objects.get(id=locked_item.latest_version_id)

    # Vô hiệu hóa phê duyệt cũ còn hiệu lực nếu có
    now = timezone.now()
    ContentApproval.objects.filter(item=locked_item, invalidated_at__isnull=True).update(
        invalidated_at=now,
        invalidation_reason="Được thay thế bởi phê duyệt mới.",
    )

    # Tạo phê duyệt mới
    approval = ContentApproval.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=target_version,
        approved_by=user,
        idempotency_key=clean_idemp,
    )

    # Ghi nhận ReviewDecision append-only
    actor_membership = get_active_membership(user, locked_item.workspace)
    ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=target_version,
        decision="APPROVE",
        actor_membership=actor_membership,
        idempotency_key=clean_idemp,
    )

    locked_item.state = ContentItemState.READY_TO_PUBLISH
    locked_item.approval_id = approval.id
    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "approval_id", "row_version", "updated_at"])

    # Mở Task PUBLISH sang READY
    pub_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.PUBLISH).first()
    if pub_task and pub_task.status == TaskStatus.WAITING:
        pub_task.status = TaskStatus.READY
        pub_task.save(update_fields=["status", "updated_at"])

    return approval, locked_item


@transaction.atomic
def owner_request_changes(
    *,
    user: Any,
    item: ContentItem,
    return_stage: str,
    reason: str,
    expected_row_version: Any = None,
) -> tuple[ReviewDecision, ContentItem]:
    """
    Chủ workspace yêu cầu sửa lại và chỉ định bước trả về (Spec F05, 6.1, 6.2, B06):
    - Quyền: AccessRole.OWNER.
    - Trạng thái bài phải là OWNER_REVIEW.
    - return_stage: "WRITING" hoặc "EDITING".
    - Bắt buộc có lý do sửa (không để trống).
    - Nếu trả về "WRITING": bài chuyển sang WRITING; Task WRITE chuyển sang READY; Task EDIT về WAITING.
    - Nếu trả về "EDITING": bài chuyển sang EDITING; Task EDIT chuyển sang READY.
    - Ghi nhận ReviewDecision append-only (decision="REQUEST_CHANGES", return_stage, reason).
    """
    _check_owner_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    _verify_row_version(locked_item.row_version, expected_row_version)

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.OWNER_REVIEW:
        raise ValidationError(
            f"Chỉ có thể yêu cầu sửa khi bài viết đang ở trạng thái Chờ Chủ duyệt (OWNER_REVIEW). Trạng thái hiện tại: '{locked_item.get_state_display()}'."
        )

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Yêu cầu chỉnh sửa bắt buộc phải nêu rõ lý do và hướng dẫn cụ thể.")

    clean_stage = (return_stage or "").strip().upper()
    if clean_stage not in ("WRITING", "EDITING"):
        raise ValidationError("Công đoạn trả về phải là Viết bài (WRITING) hoặc Biên tập (EDITING).")

    actor_membership = get_active_membership(user, locked_item.workspace)
    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="REQUEST_CHANGES",
        return_stage=clean_stage,
        reason=clean_reason,
        actor_membership=actor_membership,
    )

    if clean_stage == "WRITING":
        locked_item.state = ContentItemState.WRITING
        # Mở lại nhiệm vụ viết, đưa nhiệm vụ biên tập về WAITING (Spec 6.2)
        write_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.WRITE).first()
        if write_task:
            write_task.status = TaskStatus.READY
            write_task.save(update_fields=["status", "updated_at"])
        edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
        if edit_task:
            edit_task.status = TaskStatus.WAITING
            edit_task.save(update_fields=["status", "updated_at"])
    else:
        locked_item.state = ContentItemState.EDITING
        # Mở lại nhiệm vụ biên tập (Spec 6.2)
        edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
        if edit_task:
            edit_task.status = TaskStatus.READY
            edit_task.save(update_fields=["status", "updated_at"])

    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "row_version", "updated_at"])

    return decision, locked_item


@transaction.atomic
def withdraw_review(
    *,
    user: Any,
    item: ContentItem,
    reason: str,
    expected_row_version: Any = None,
) -> tuple[ReviewDecision, ContentItem]:
    """
    Rút gửi duyệt có lý do (Spec F05, 6.1):
    - Quyền: Người biên tập được phân công hoặc Chủ workspace.
    - Trạng thái bài phải là OWNER_REVIEW.
    - Bắt buộc có lý do rút gửi duyệt.
    - Chuyển trạng thái: OWNER_REVIEW -> EDITING.
    - Mở lại Task EDIT: chuyển status sang READY.
    - Ghi nhận ReviewDecision append-only (decision="WITHDRAW_REVIEW", return_stage="EDITING", reason).
    """
    actor_membership = _check_editor_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    _verify_row_version(locked_item.row_version, expected_row_version)

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.OWNER_REVIEW:
        raise ValidationError(
            f"Chỉ có thể rút duyệt khi bài viết đang ở trạng thái Chờ Chủ duyệt (OWNER_REVIEW). Trạng thái hiện tại: '{locked_item.get_state_display()}'."
        )

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Rút bài gửi duyệt bắt buộc phải cung cấp lý do.")

    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="WITHDRAW_REVIEW",
        return_stage="EDITING",
        reason=clean_reason,
        actor_membership=actor_membership,
    )

    locked_item.state = ContentItemState.EDITING
    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "row_version", "updated_at"])

    edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
    if edit_task:
        edit_task.status = TaskStatus.READY
        edit_task.save(update_fields=["status", "updated_at"])

    return decision, locked_item


@transaction.atomic
def reopen_content_item(
    *,
    user: Any,
    item: ContentItem,
    reason: str,
    expected_row_version: Any = None,
) -> tuple[ReviewDecision, ContentItem]:
    """
    Chủ workspace mở lại bài viết (Spec F05, F06, 6.1, 6.2, AC09, B06):
    - Chỉ Chủ workspace mới có quyền mở lại (AccessRole.OWNER).
    - Áp dụng khi bài viết đang ở READY_TO_PUBLISH hoặc PUBLISHED.
    - Bắt buộc có lý do mở lại.
    - Vô hiệu hóa ContentApproval hiện tại: gán invalidated_at và invalidation_reason (AC09).
    - Xóa approval_id trên ContentItem (approval_id = None).
    - Chuyển trạng thái ContentItem: -> EDITING.
    - Nhiệm vụ EDIT chuyển sang READY; nhiệm vụ PUBLISH nếu đang READY chuyển về WAITING.
    - Nếu gói nội dung đang COMPLETED, tự động chuyển về ACTIVE (Spec 6.2).
    - Ghi nhận ReviewDecision append-only (decision="REOPEN", return_stage="EDITING", reason).
    """
    _check_owner_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    _verify_row_version(locked_item.row_version, expected_row_version)

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state not in (ContentItemState.READY_TO_PUBLISH, ContentItemState.PUBLISHED):
        raise ValidationError(
            f"Chỉ có thể mở lại khi bài viết đang ở trạng thái 'Chờ đăng' (READY_TO_PUBLISH) hoặc 'Đã đăng' (PUBLISHED). Hiện tại: '{locked_item.get_state_display()}'."
        )

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Mở lại bài viết bắt buộc phải cung cấp lý do.")

    # AC09: Vô hiệu hóa toàn bộ ContentApproval của bài viết
    now = timezone.now()
    ContentApproval.objects.filter(item=locked_item, invalidated_at__isnull=True).update(
        invalidated_at=now,
        invalidation_reason=f"Chủ workspace mở lại bài viết với lý do: {clean_reason}",
    )

    actor_membership = get_active_membership(user, locked_item.workspace)
    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="REOPEN",
        return_stage="EDITING",
        reason=clean_reason,
        actor_membership=actor_membership,
    )

    locked_item.approval_id = None
    locked_item.state = ContentItemState.EDITING
    locked_item.row_version += 1
    locked_item.save(update_fields=["approval_id", "state", "row_version", "updated_at"])

    # Task transitions (Spec 6.2)
    edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
    if edit_task:
        edit_task.status = TaskStatus.READY
        edit_task.save(update_fields=["status", "updated_at"])

    pub_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.PUBLISH).first()
    if pub_task and pub_task.status == TaskStatus.READY:
        pub_task.status = TaskStatus.WAITING
        pub_task.save(update_fields=["status", "updated_at"])

    # Spec 6.2: Mở lại bài làm gói COMPLETED trở lại ACTIVE
    _sync_package_status(locked_item.package_id)

    return decision, locked_item


@transaction.atomic
def cancel_content_item(
    *,
    user: Any,
    item: ContentItem,
    reason: str,
    expected_row_version: Any = None,
) -> tuple[ReviewDecision, ContentItem]:
    """
    Chủ workspace hủy bài viết có lý do (Spec 6.1: TODO / WRITING / EDITING / OWNER_REVIEW / READY_TO_PUBLISH -> CANCELLED):
    - Quyền: Chủ workspace (AccessRole.OWNER).
    - Trạng thái bài: không cho phép hủy bài đã PUBLISHED hoặc đã CANCELLED.
    - Bắt buộc có lý do hủy.
    - Nếu bài đang ở READY_TO_PUBLISH: thu hồi duyệt, vô hiệu hóa ContentApproval (Spec 6.1).
    - Trạng thái bài chuyển sang CANCELLED.
    - Tất cả Task chưa hoàn thành (status != DONE) chuyển sang CANCELLED.
    - Ghi nhận ReviewDecision append-only (decision="CANCEL", reason).
    """
    _check_owner_access(user, item)

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    _verify_row_version(locked_item.row_version, expected_row_version)

    if locked_item.state == ContentItemState.PUBLISHED:
        raise ValidationError("Không thể hủy bài viết đã xuất bản (PUBLISHED). Để xử lý, hãy mở lại bài viết.")

    if locked_item.state == ContentItemState.CANCELLED:
        raise ValidationError("Bài viết này đã được hủy trước đó.")

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Hủy bài viết bắt buộc phải cung cấp lý do.")

    now = timezone.now()
    # Nếu đang READY_TO_PUBLISH: vô hiệu hóa duyệt (Spec 6.1)
    if locked_item.state == ContentItemState.READY_TO_PUBLISH:
        ContentApproval.objects.filter(item=locked_item, invalidated_at__isnull=True).update(
            invalidated_at=now,
            invalidation_reason=f"Bài viết bị hủy bởi Chủ workspace: {clean_reason}",
        )
        locked_item.approval_id = None

    actor_membership = get_active_membership(user, locked_item.workspace)
    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="CANCEL",
        reason=clean_reason,
        actor_membership=actor_membership,
    )

    locked_item.state = ContentItemState.CANCELLED
    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "approval_id", "row_version", "updated_at"])

    # Cập nhật các Task chưa DONE sang CANCELLED
    Task.objects.filter(item=locked_item).exclude(status=TaskStatus.DONE).update(
        status=TaskStatus.CANCELLED,
        updated_at=now,
    )

    # Cập nhật trạng thái gói nếu cần
    _sync_package_status(locked_item.package_id)

    return decision, locked_item


@transaction.atomic
def block_content_item(
    *,
    user: Any,
    item: ContentItem,
    reason: str,
    expected_row_version: Any = None,
) -> ContentItem:
    """
    Báo bài viết bị chặn (Spec F07, 6.1, AC12, B06):
    - Quyền: Người thực hiện (viết, biên tập, xuất bản) hoặc Chủ workspace (ACTIVE membership).
    - Bắt buộc có lý do bị chặn.
    - Ghi nhận blocked_reason, blocked_by=user, blocked_at=now.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")
    membership = get_active_membership(user, item.workspace)
    if not membership or not membership.is_active:
        raise PermissionDenied("Không có quyền truy cập.")

    is_assigned = (
        item.writer_membership_id == membership.id
        or item.editor_membership_id == membership.id
        or item.publisher_membership_id == membership.id
    )
    if membership.access_role != AccessRole.OWNER and not is_assigned:
        raise PermissionDenied("Chỉ người được phân công hoặc Chủ workspace mới có thể báo chặn bài viết.")

    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Báo chặn bài viết bắt buộc phải cung cấp lý do.")

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    _verify_row_version(locked_item.row_version, expected_row_version)

    locked_item.blocked_reason = clean_reason
    locked_item.blocked_by = user
    locked_item.blocked_at = timezone.now()
    locked_item.row_version += 1
    locked_item.save(update_fields=["blocked_reason", "blocked_by", "blocked_at", "row_version", "updated_at"])

    return locked_item


@transaction.atomic
def unblock_content_item(
    *,
    user: Any,
    item: ContentItem,
    resolution_note: str = "",
    expected_row_version: Any = None,
) -> ContentItem:
    """
    Giải quyết và gỡ chặn bài viết (Spec F07, 6.1, AC12, B06):
    - Quyền: Chủ workspace hoặc người phụ trách công đoạn hiện tại (viết khi WRITING, biên tập khi EDITING...).
    - Xóa blocked_reason, blocked_by, blocked_at; ghi nhận resolution_note.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Yêu cầu đăng nhập.")
    membership = get_active_membership(user, item.workspace)
    if not membership or not membership.is_active:
        raise PermissionDenied("Không có quyền truy cập.")

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)
    if not locked_item.is_blocked:
        raise ValidationError("Bài viết hiện không ở trạng thái bị chặn.")

    # Kiểm tra người phụ trách bước hiện tại hoặc Chủ
    is_responsible = False
    if membership.access_role == AccessRole.OWNER:
        is_responsible = True
    elif locked_item.state in (ContentItemState.TODO, ContentItemState.WRITING) and locked_item.writer_membership_id == membership.id:
        is_responsible = True
    elif locked_item.state == ContentItemState.EDITING and locked_item.editor_membership_id == membership.id:
        is_responsible = True
    elif locked_item.state == ContentItemState.READY_TO_PUBLISH and locked_item.publisher_membership_id == membership.id:
        is_responsible = True

    if not is_responsible:
        raise PermissionDenied("Chỉ Chủ workspace hoặc người đang chịu trách nhiệm bước này mới có quyền gỡ chặn.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    clean_note = (resolution_note or "").strip()
    locked_item.blocked_reason = ""
    locked_item.blocked_by = None
    locked_item.blocked_at = None
    locked_item.resolution_note = clean_note
    locked_item.row_version += 1
    locked_item.save(update_fields=["blocked_reason", "blocked_by", "blocked_at", "resolution_note", "row_version", "updated_at"])

    return locked_item


@transaction.atomic
def submit_for_owner_review(
    *,
    user: Any,
    item: ContentItem,
    checklist: dict[str, Any],
    expected_row_version: Any = None,
    idempotency_key: str = "",
) -> tuple[ReviewDecision, ContentItem]:
    """
    Biên tập viên đánh dấu hoàn tất checklist và chuyển Chủ duyệt (Spec F04, 6.1, 6.2, B05):
    - Bắt buộc kiểm tra cả 4 mục trong checklist:
      1. brief_compliance: True (Đúng brief)
      2. factual_accuracy: True (Độ chính xác theo tài liệu)
      3. voice_tone: True (Giọng văn thương hiệu)
      4. cta_verified: True (Kêu gọi hành động CTA)
    - Chuyển trạng thái: EDITING -> OWNER_REVIEW.
    - Task EDIT: chuyển thành DONE.
    - Lưu ReviewDecision append-only kèm checklist.
    """
    actor_membership = _check_editor_access(user, item)

    clean_idemp = (idempotency_key or "").strip()

    # Kiểm tra 4 mục bắt buộc trong checklist
    required_keys = ["brief_compliance", "factual_accuracy", "voice_tone", "cta_verified"]
    missing_labels = {
        "brief_compliance": "Đúng brief nội dung",
        "factual_accuracy": "Độ chính xác theo tài liệu",
        "voice_tone": "Đúng giọng văn thương hiệu",
        "cta_verified": "Kiểm tra kêu gọi hành động (CTA)",
    }
    for k in required_keys:
        if not checklist.get(k):
            raise ValidationError(f"Mục checklist chưa hoàn thành: '{missing_labels.get(k, k)}'.")

    locked_item = ContentItem.objects.select_for_update().get(id=item.id)

    if clean_idemp:
        existing_decision = ReviewDecision.objects.filter(
            item=locked_item, decision="SUBMIT_REVIEW", idempotency_key=clean_idemp
        ).first()
        if existing_decision:
            return existing_decision, locked_item

    if locked_item.is_blocked:
        raise ValidationError(f"Bài viết đang bị chặn vì lý do: '{locked_item.blocked_reason}'.")

    if locked_item.state != ContentItemState.EDITING:
        raise ValidationError(f"Chỉ có thể nộp duyệt khi bài đang ở trạng thái Biên tập. Hiện tại: '{locked_item.get_state_display()}'.")

    if not locked_item.latest_version_id:
        raise ValidationError("Bài viết chưa có phiên bản nội dung nào để nộp duyệt.")

    _verify_row_version(locked_item.row_version, expected_row_version)

    clean_checklist = {k: bool(checklist.get(k)) for k in required_keys}

    decision = ReviewDecision.objects.create(
        workspace=locked_item.workspace,
        item=locked_item,
        version=locked_item.latest_version,
        decision="SUBMIT_REVIEW",
        checklist=clean_checklist,
        actor_membership=actor_membership,
        idempotency_key=clean_idemp,
    )

    locked_item.state = ContentItemState.OWNER_REVIEW
    locked_item.row_version += 1
    locked_item.save(update_fields=["state", "row_version", "updated_at"])

    edit_task = Task.objects.select_for_update().filter(item=locked_item, role=TaskRole.EDIT).first()
    if edit_task:
        edit_task.status = TaskStatus.DONE
        edit_task.save(update_fields=["status", "updated_at"])

    return decision, locked_item

