import uuid
from typing import Any
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import AccessRole, BrandProfile, EmploymentType, Membership, MembershipStatus, Workspace, validate_timezone
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

    # 2. Khóa dòng BrandProfile để đảm bảo tính tuần tự
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
        brand_profile.save()
        return brand_profile

