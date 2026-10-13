import uuid
import zoneinfo
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_timezone(value: str) -> None:
    if not value or value.strip() not in zoneinfo.available_timezones():
        raise ValidationError(f"Múi giờ '{value}' không hợp lệ theo chuẩn IANA.")


class AccessRole(models.TextChoices):
    OWNER = "OWNER", "Chủ workspace"
    MEMBER = "MEMBER", "Thành viên"


class EmploymentType(models.TextChoices):
    IN_HOUSE = "IN_HOUSE", "Nội bộ"
    FREELANCER = "FREELANCER", "Freelancer / Đối tác ngoài"


class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Đang hoạt động"
    INACTIVE = "INACTIVE", "Vô hiệu hóa"
    INVITED = "INVITED", "Đang mời"


class Workspace(models.Model):
    """
    Workspace là ranh giới cô lập dữ liệu (tenant isolation boundary).
    Mỗi workspace có duy nhất một owner_user là Chủ.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Mã định danh (UUID)",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Tên workspace",
    )
    timezone = models.CharField(
        max_length=50,
        default="Asia/Ho_Chi_Minh",
        validators=[validate_timezone],
        verbose_name="Múi giờ",
    )
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_workspaces",
        verbose_name="Chủ workspace",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Workspace"
        verbose_name_plural = "Workspaces"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.name:
            self.name = self.name.strip()
            if not self.name:
                raise ValidationError({"name": "Tên workspace không được chỉ chứa khoảng trắng."})
            if len(self.name) > 100:
                raise ValidationError({"name": "Tên workspace không được vượt quá 100 ký tự."})
        else:
            raise ValidationError({"name": "Tên workspace không được để trống."})

        if self.timezone:
            self.timezone = self.timezone.strip()
            validate_timezone(self.timezone)


class Membership(models.Model):
    """
    Gắn kết người dùng với workspace theo vai trò và trạng thái cụ thể.
    Ràng buộc: một người dùng chỉ có tối đa một membership trong một workspace.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Mã định danh (UUID)",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="Workspace",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
        verbose_name="Thành viên",
    )
    access_role = models.CharField(
        max_length=20,
        choices=AccessRole.choices,
        default=AccessRole.MEMBER,
        verbose_name="Vai trò truy cập",
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.IN_HOUSE,
        verbose_name="Hình thức quan hệ",
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
        verbose_name="Trạng thái",
    )
    ai_use_allowed = models.BooleanField(
        default=False,
        verbose_name="Cho phép dùng AI",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Thành viên Workspace"
        verbose_name_plural = "Thành viên Workspace"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                name="unique_workspace_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username} @ {self.workspace.name} ({self.get_access_role_display()})"

    @property
    def is_owner(self) -> bool:
        return self.access_role == AccessRole.OWNER

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE

class InvitationStatus(models.TextChoices):
    PENDING = "PENDING", "Đang chờ"
    ACCEPTED = "ACCEPTED", "Đã chấp nhận"
    REVOKED = "REVOKED", "Đã thu hồi"
    EXPIRED = "EXPIRED", "Đã hết hạn"


class Invitation(models.Model):
    """
    Lời mời tham gia workspace gửi tới một địa chỉ email.
    Theo Spec mục 3.2 và 9:
    - Token được lưu dạng SHA-256 hash (token_hash unique), không lưu raw token trong CSDL.
    - Hết hạn sau 7 ngày, dùng một lần duy nhất.
    - Không thể mời vai trò OWNER.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Mã định danh (UUID)",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name="Workspace",
    )
    email = models.EmailField(
        max_length=254,
        db_index=True,
        verbose_name="Email được mời (đã chuẩn hóa)",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="Mã băm token (SHA-256)",
    )
    access_role = models.CharField(
        max_length=20,
        choices=AccessRole.choices,
        default=AccessRole.MEMBER,
        verbose_name="Vai trò được mời",
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.IN_HOUSE,
        verbose_name="Hình thức quan hệ",
    )
    ai_use_allowed = models.BooleanField(
        default=False,
        verbose_name="Cho phép dùng AI",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_workspace_invitations",
        verbose_name="Người gửi lời mời",
    )
    expires_at = models.DateTimeField(verbose_name="Thời điểm hết hạn")
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm chấp nhận")
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm thu hồi")
    last_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm gửi gần nhất")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Lời mời Workspace"
        verbose_name_plural = "Lời mời Workspace"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "email"], name="idx_invitation_ws_email"),
            models.Index(fields=["token_hash"], name="idx_invitation_token_hash"),
        ]

    def __str__(self) -> str:
        return f"Lời mời {self.email} -> {self.workspace.name} ({self.status_display})"

    @property
    def is_pending(self) -> bool:
        from django.utils import timezone

        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at <= timezone.now()
        )

    @property
    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def status_display(self) -> str:
        if self.is_accepted:
            return "Đã chấp nhận"
        if self.is_revoked:
            return "Đã thu hồi"
        if self.is_expired:
            return "Đã hết hạn"
        return "Đang chờ"

    def clean(self) -> None:
        super().clean()
        if self.access_role == AccessRole.OWNER:
            raise ValidationError("Không thể tạo lời mời cho vai trò Chủ workspace (OWNER).")

