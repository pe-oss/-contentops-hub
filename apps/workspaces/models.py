import uuid
from typing import Any

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



class BrandProfile(models.Model):
    """
    Hồ sơ thương hiệu của Workspace theo Spec mục 4, 9, 14 và B03:
    - Một workspace có đúng một hồ sơ thương hiệu (OneToOne unique).
    - Lưu phiên bản (revision) tự động tăng sau mỗi lần sửa.
    - Giữ snapshot độc lập cho các gói content (snapshot cũ không bị thay đổi).
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Mã định danh (UUID)",
    )
    workspace = models.OneToOneField(
        Workspace,
        on_delete=models.CASCADE,
        related_name="brand_profile",
        verbose_name="Workspace",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Tên thương hiệu",
        help_text="Từ 1 đến 100 ký tự. Bắt buộc.",
    )
    product_summary = models.TextField(
        max_length=5000,
        verbose_name="Sản phẩm / Dịch vụ",
        help_text="Mô tả sản phẩm, dịch vụ chủ lực từ 1 đến 5.000 ký tự. Bắt buộc.",
    )
    target_audience = models.TextField(
        max_length=3000,
        verbose_name="Khách hàng mục tiêu",
        help_text="Chân dung đối tượng mục tiêu từ 1 đến 3.000 ký tự. Bắt buộc.",
    )
    tone_of_voice = models.TextField(
        max_length=3000,
        blank=True,
        default="",
        verbose_name="Giọng văn thương hiệu",
    )
    avoid_guidelines = models.TextField(
        max_length=3000,
        blank=True,
        default="",
        verbose_name="Điều cần tránh",
    )
    allowed_claims = models.TextField(
        max_length=3000,
        blank=True,
        default="",
        verbose_name="Tuyên bố được phép",
    )
    source_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="URL nguồn tham khảo",
    )
    revision = models.PositiveIntegerField(
        default=1,
        verbose_name="Phiên bản hồ sơ (Revision)",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_brand_profiles",
        verbose_name="Người cập nhật gần nhất",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Hồ sơ thương hiệu"
        verbose_name_plural = "Hồ sơ thương hiệu"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.name} (Rev {self.revision}) @ {self.workspace.name}"

    def clean(self) -> None:
        super().clean()
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": "Tên thương hiệu không được để trống hoặc chỉ có khoảng trắng."})
        if len(self.name) > 100:
            raise ValidationError({"name": "Tên thương hiệu không được vượt quá 100 ký tự."})

        self.product_summary = (self.product_summary or "").strip()
        if not self.product_summary:
            raise ValidationError({"product_summary": "Thông tin sản phẩm/dịch vụ không được để trống."})
        if len(self.product_summary) > 5000:
            raise ValidationError({"product_summary": "Thông tin sản phẩm không được vượt quá 5.000 ký tự."})

        self.target_audience = (self.target_audience or "").strip()
        if not self.target_audience:
            raise ValidationError({"target_audience": "Khách hàng mục tiêu không được để trống."})
        if len(self.target_audience) > 3000:
            raise ValidationError({"target_audience": "Khách hàng mục tiêu không được vượt quá 3.000 ký tự."})

        self.tone_of_voice = (self.tone_of_voice or "").strip()
        if len(self.tone_of_voice) > 3000:
            raise ValidationError({"tone_of_voice": "Giọng văn không được vượt quá 3.000 ký tự."})

        self.avoid_guidelines = (self.avoid_guidelines or "").strip()
        if len(self.avoid_guidelines) > 3000:
            raise ValidationError({"avoid_guidelines": "Điều cần tránh không được vượt quá 3.000 ký tự."})

        self.allowed_claims = (self.allowed_claims or "").strip()
        if len(self.allowed_claims) > 3000:
            raise ValidationError({"allowed_claims": "Tuyên bố được phép không được vượt quá 3.000 ký tự."})

        if not isinstance(self.source_urls, list):
            raise ValidationError({"source_urls": "Danh sách URL phải là một danh sách hợp lệ."})

        import urllib.parse

        if len(self.source_urls) > 10:
            raise ValidationError({"source_urls": "Tối đa 10 URL nguồn tham khảo."})

        cleaned_urls = []
        for url_item in self.source_urls:
            raw = str(url_item or "").strip()
            if not raw:
                continue
            parsed = urllib.parse.urlparse(raw)
            if parsed.scheme.lower() != "https":
                raise ValidationError({"source_urls": f"URL '{raw}' không hợp lệ. Chỉ chấp nhận giao thức HTTPS."})
            if not parsed.netloc:
                raise ValidationError({"source_urls": f"URL '{raw}' không hợp lệ. Phải có tên miền đầy đủ."})
            cleaned_urls.append(raw)

        if len(cleaned_urls) > 10:
            raise ValidationError({"source_urls": "Tối đa 10 URL nguồn tham khảo."})
        self.source_urls = cleaned_urls

    def to_snapshot(self) -> dict[str, Any]:
        """
        Xuất snapshot bất biến của hồ sơ thương hiệu tại revision hiện tại.
        Dùng để nhúng vào Gói nội dung (Packages) theo Spec F02 và AC15.
        Snapshot này hoàn toàn độc lập với BrandProfile gốc, bao gồm các dữ liệu mutable như source_urls.
        Sửa hồ sơ hoặc danh sách URL sau đó tuyệt đối không làm thay đổi dữ liệu của snapshot đã xuất.
        Lưu ý: Chưa đánh dấu tích hợp vào gói content khi Milestone B04 chưa hoàn tất.
        """
        return {
            "brand_profile_id": str(self.id),
            "brand_name": str(self.name),
            "product_summary": str(self.product_summary),
            "target_audience": str(self.target_audience),
            "tone_of_voice": str(self.tone_of_voice or ""),
            "avoid_guidelines": str(self.avoid_guidelines or ""),
            "allowed_claims": str(self.allowed_claims or ""),
            "source_urls": [str(u) for u in (self.source_urls or [])],
            "revision": int(self.revision),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class PackageStatus(models.TextChoices):
    DRAFT = "DRAFT", "Kế hoạch nháp"
    ACTIVE = "ACTIVE", "Đang thực hiện"
    COMPLETED = "COMPLETED", "Đã hoàn thành"
    CANCELLED = "CANCELLED", "Đã hủy"


class ContentItemState(models.TextChoices):
    TODO = "TODO", "Chờ thực hiện"
    WRITING = "WRITING", "Đang viết"
    EDITING = "EDITING", "Đang biên tập"
    OWNER_REVIEW = "OWNER_REVIEW", "Chủ duyệt"
    READY_TO_PUBLISH = "READY_TO_PUBLISH", "Chờ đăng"
    PUBLISHED = "PUBLISHED", "Đã đăng"
    CANCELLED = "CANCELLED", "Đã hủy"


class TaskRole(models.TextChoices):
    WRITE = "WRITE", "Viết bài"
    EDIT = "EDIT", "Biên tập"
    PUBLISH = "PUBLISH", "Xuất bản"


class TaskStatus(models.TextChoices):
    WAITING = "WAITING", "Chờ bước trước"
    READY = "READY", "Sẵn sàng"
    IN_PROGRESS = "IN_PROGRESS", "Đang làm"
    DONE = "DONE", "Hoàn thành"
    CANCELLED = "CANCELLED", "Đã hủy"


class TaskExecutionMode(models.TextChoices):
    MANUAL = "MANUAL", "Thủ công"
    EXTERNAL_AI = "EXTERNAL_AI", "AI bên ngoài"
    BYOK = "BYOK", "BYOK AI"


class Package(models.Model):
    """
    Gói nội dung (Package) - Spec mục 4, 5 F02, 9, 13 B04:
    - Ranh giới quản lý đợt content marketing trong Workspace.
    - Chứa thông tin mục tiêu, kênh (mặc định FACEBOOK), thời gian và người điều phối.
    - Snapshot thương hiệu được lưu vào gói khi Chủ duyệt kế hoạch.
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
        related_name="packages",
        verbose_name="Workspace",
    )
    coordinator_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="coordinated_packages",
        verbose_name="Thành viên điều phối",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="Tên gói nội dung",
    )
    objective = models.TextField(
        max_length=3000,
        verbose_name="Mục tiêu của gói",
    )
    channel = models.CharField(
        max_length=50,
        default="FACEBOOK",
        verbose_name="Kênh xuất bản",
    )
    start_date = models.DateField(
        verbose_name="Ngày bắt đầu",
    )
    end_date = models.DateField(
        verbose_name="Ngày kết thúc",
    )
    status = models.CharField(
        max_length=20,
        choices=PackageStatus.choices,
        default=PackageStatus.DRAFT,
        verbose_name="Trạng thái gói",
    )
    plan_revision = models.PositiveIntegerField(
        default=1,
        verbose_name="Phiên bản kế hoạch (Plan Revision)",
    )
    brand_snapshot = models.JSONField(
        null=True,
        blank=True,
        default=dict,
        verbose_name="Snapshot hồ sơ thương hiệu",
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời điểm lưu trữ",
    )
    row_version = models.PositiveIntegerField(
        default=1,
        verbose_name="Phiên bản dòng (Row Version)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Gói nội dung"
        verbose_name_plural = "Gói nội dung"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"], name="idx_package_ws_status"),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}] @ {self.workspace.name}"

    def clean(self) -> None:
        super().clean()
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": "Tên gói nội dung không được để trống."})
        if len(self.name) > 150:
            raise ValidationError({"name": "Tên gói nội dung không được vượt quá 150 ký tự."})

        self.objective = (self.objective or "").strip()
        if not self.objective:
            raise ValidationError({"objective": "Mục tiêu của gói không được để trống."})
        if len(self.objective) > 3000:
            raise ValidationError({"objective": "Mục tiêu của gói không được vượt quá 3.000 ký tự."})

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Ngày kết thúc không được trước ngày bắt đầu."})

        if self.coordinator_membership_id and self.workspace_id:
            if self.coordinator_membership.workspace_id != self.workspace_id:
                raise ValidationError({"coordinator_membership": "Thành viên điều phối phải thuộc cùng workspace với gói."})
            if not self.coordinator_membership.is_active:
                raise ValidationError({"coordinator_membership": "Thành viên điều phối phải đang hoạt động (ACTIVE)."})

    @property
    def is_draft(self) -> bool:
        return self.status == PackageStatus.DRAFT

    @property
    def is_active(self) -> bool:
        return self.status == PackageStatus.ACTIVE

class PlanApproval(models.Model):
    """
    Bản ghi phê duyệt kế hoạch (Spec mục 4, 9, 13 B04):
    - Chụp lại toàn bộ snapshot bất biến của kế hoạch và brand tại thời điểm Chủ duyệt.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="Mã định danh (UUID)",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="plan_approvals",
        verbose_name="Gói nội dung",
    )
    plan_revision = models.PositiveIntegerField(
        verbose_name="Phiên bản kế hoạch được duyệt",
    )
    immutable_plan_snapshot = models.JSONField(
        verbose_name="Snapshot kế hoạch bất biến",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_plans",
        verbose_name="Chủ workspace duyệt",
    )
    idempotency_key = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Khóa Idempotency chống nhấp đôi",
    )
    approved_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm duyệt")

    class Meta:
        verbose_name = "Bản ghi duyệt kế hoạch"
        verbose_name_plural = "Bản ghi duyệt kế hoạch"
        ordering = ["-approved_at"]

    def __str__(self) -> str:
        return f"Duyệt plan rev {self.plan_revision} - {self.package.name} @ {self.approved_at}"


class ContentItem(models.Model):
    """
    Bài viết trong kế hoạch nội dung (ContentItem) - Spec mục 4, 5, 9, 13:
    - Thuộc một Gói nội dung và Workspace.
    - Chứa brief, CTA, các mốc hạn (viết <= biên tập <= duyệt <= đăng) và 3 vai trò phân công.
    - Tối đa 50 bài/gói.
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
        related_name="content_items",
        verbose_name="Workspace",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Gói nội dung",
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Tiêu đề bài viết",
    )
    brief = models.TextField(
        max_length=5000,
        verbose_name="Yêu cầu / Brief nội dung",
    )
    cta = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Kêu gọi hành động (CTA)",
    )
    state = models.CharField(
        max_length=20,
        choices=ContentItemState.choices,
        default=ContentItemState.TODO,
        verbose_name="Trạng thái bài viết",
    )
    writing_deadline = models.DateTimeField(
        verbose_name="Hạn viết bài",
    )
    editing_deadline = models.DateTimeField(
        verbose_name="Hạn biên tập",
    )
    review_deadline = models.DateTimeField(
        verbose_name="Hạn Chủ duyệt",
    )
    planned_publish_at = models.DateTimeField(
        verbose_name="Thời điểm dự kiến đăng",
    )
    writer_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="assigned_writing_items",
        verbose_name="Người viết bài",
    )
    editor_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="assigned_editing_items",
        verbose_name="Người biên tập",
    )
    publisher_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="assigned_publishing_items",
        verbose_name="Người xuất bản",
    )
    blocked_reason = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Lý do bị chặn",
    )
    blocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocked_content_items",
        verbose_name="Người báo bị chặn",
    )
    blocked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời điểm bị chặn",
    )
    resolution_note = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Ghi chú giải quyết chặn",
    )
    latest_version_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name="Mã phiên bản mới nhất (B05)",
    )
    approval_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name="Mã phê duyệt hợp lệ (B06)",
    )
    row_version = models.PositiveIntegerField(
        default=1,
        verbose_name="Phiên bản dòng (Row Version)",
    )
    draft_text = models.TextField(
        blank=True,
        default="",
        verbose_name="Bản nháp đang viết (B05)",
    )
    draft_reference_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="URLs tham khảo bản nháp (B05)",
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Thứ tự hiển thị",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Bài viết trong kế hoạch"
        verbose_name_plural = "Bài viết trong kế hoạch"
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["workspace", "package", "state"], name="idx_item_ws_pkg_state"),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.get_state_display()}] ({self.package.name})"
    @property
    def is_blocked(self) -> bool:
        """Kiểm tra bài viết có đang bị cờ chặn hay không (Spec 6.1, AC12)."""
        return bool(self.blocked_reason and self.blocked_reason.strip())

    @property
    def latest_version(self):
        """Lấy phiên bản mới nhất gắn với latest_version_id."""
        if not self.latest_version_id:
            return None
        return self.versions.filter(id=self.latest_version_id).first()


    def clean(self) -> None:
        super().clean()
        self.title = (self.title or "").strip()
        if not self.title:
            raise ValidationError({"title": "Tiêu đề bài viết không được để trống."})
        if len(self.title) > 200:
            raise ValidationError({"title": "Tiêu đề bài viết không được vượt quá 200 ký tự."})

        self.brief = (self.brief or "").strip()
        if not self.brief:
            raise ValidationError({"brief": "Brief bài viết không được để trống."})
        if len(self.brief) > 5000:
            raise ValidationError({"brief": "Brief bài viết không được vượt quá 5.000 ký tự."})

        if self.cta:
            self.cta = self.cta.strip()
            if len(self.cta) > 500:
                raise ValidationError({"cta": "Kêu gọi hành động (CTA) không được vượt quá 500 ký tự."})

        # Kiểm tra tính nhất quán workspace giữa package và content item
        if self.package_id and self.workspace_id:
            if self.package.workspace_id != self.workspace_id:
                raise ValidationError({"package": "Gói nội dung không thuộc cùng workspace với bài viết."})

        # Kiểm tra tính nhất quán workspace cho 3 vai trò
        for field_name, member in [
            ("writer_membership", getattr(self, "writer_membership", None)),
            ("editor_membership", getattr(self, "editor_membership", None)),
            ("publisher_membership", getattr(self, "publisher_membership", None)),
        ]:
            if member and self.workspace_id:
                if member.workspace_id != self.workspace_id:
                    raise ValidationError({field_name: "Thành viên được phân công phải thuộc cùng workspace."})
                if not member.is_active:
                    raise ValidationError({field_name: "Thành viên được phân công phải đang hoạt động (ACTIVE)."})

        # Kiểm tra trật tự deadline theo Spec mục 4: viết <= biên tập <= duyệt <= đăng
        if self.writing_deadline and self.editing_deadline and self.writing_deadline > self.editing_deadline:
            raise ValidationError({"editing_deadline": "Hạn biên tập không được trước hạn viết."})

        if self.editing_deadline and self.review_deadline and self.editing_deadline > self.review_deadline:
            raise ValidationError({"review_deadline": "Hạn duyệt không được trước hạn biên tập."})

        if self.review_deadline and self.planned_publish_at and self.review_deadline > self.planned_publish_at:
            raise ValidationError({"planned_publish_at": "Thời điểm dự kiến đăng không được trước hạn duyệt."})

        # Kiểm tra lịch bài nằm trong khoảng thời gian của gói
        if self.package_id:
            pkg = self.package
            if pkg.start_date and self.writing_deadline and self.writing_deadline.date() < pkg.start_date:
                raise ValidationError({"writing_deadline": f"Hạn viết ({self.writing_deadline.date()}) không được trước ngày bắt đầu gói ({pkg.start_date})."})
            if pkg.end_date and self.planned_publish_at and self.planned_publish_at.date() > pkg.end_date:
                raise ValidationError({"planned_publish_at": f"Thời điểm dự kiến đăng ({self.planned_publish_at.date()}) không được sau ngày kết thúc gói ({pkg.end_date})."})


class ContentVersion(models.Model):
    """
    Phiên bản nội dung bài viết (ContentVersion) - Spec mục 5 F03-F04, 9, 13 B05:
    - Bất biến (immutable): nộp/sửa không ghi đè, luôn sinh phiên bản mới với version_no tăng tuần tự.
    - Ràng buộc: unique(item, version_no).
    - Lưu text, reference_urls (HTTPS), source (MANUAL / EXTERNAL_AI), tác giả, phiên bản gốc.
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
        related_name="content_versions",
        verbose_name="Workspace",
    )
    item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="Bài viết",
    )
    version_no = models.PositiveIntegerField(
        verbose_name="Số thứ tự phiên bản",
    )
    text = models.TextField(
        verbose_name="Nội dung bài viết",
    )
    reference_urls = models.JSONField(
        default=list,
        blank=True,
        verbose_name="URLs tham khảo (HTTPS)",
    )
    source = models.CharField(
        max_length=20,
        choices=TaskExecutionMode.choices,
        default=TaskExecutionMode.MANUAL,
        verbose_name="Nguồn tạo",
    )
    author_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="authored_versions",
        verbose_name="Tác giả phiên bản",
    )
    parent_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_versions",
        verbose_name="Phiên bản gốc",
    )
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Khóa chống trùng lặp (Idempotency Key)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")

    class Meta:
        verbose_name = "Phiên bản nội dung"
        verbose_name_plural = "Phiên bản nội dung"
        ordering = ["version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "version_no"],
                name="unique_item_version_no",
            ),
        ]
        indexes = [
            models.Index(fields=["item", "created_at"], name="idx_ver_item_created"),
            models.Index(fields=["workspace", "created_at"], name="idx_ver_ws_created"),
        ]

    def __str__(self) -> str:
        return f"{self.item.title} - v{self.version_no}"

    def save(self, *args, **kwargs):
        if not self._state.adding and ContentVersion.objects.filter(pk=self.pk).exists():
            raise ValidationError("ContentVersion là bản ghi bất biến (immutable) và không thể chỉnh sửa.")
        super().save(*args, **kwargs)


class ReviewDecision(models.Model):
    """
    Quyết định biên tập / duyệt bài viết (ReviewDecision) - Spec mục 5 F04-F05, 9, 13 B05:
    - Ghi nhận quyết định yêu cầu sửa (REQUEST_CHANGES) hoặc nộp Chủ duyệt (SUBMIT_REVIEW).
    - Append-only: lưu lịch sử các vòng kiểm tra và phản hồi.
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
        related_name="review_decisions",
        verbose_name="Workspace",
    )
    item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="review_decisions",
        verbose_name="Bài viết",
    )
    version = models.ForeignKey(
        ContentVersion,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decisions",
        verbose_name="Phiên bản xem xét",
    )
    decision = models.CharField(
        max_length=30,
        choices=[
            ("REQUEST_CHANGES", "Yêu cầu sửa"),
            ("SUBMIT_REVIEW", "Nộp Chủ duyệt"),
            ("APPROVE", "Chủ duyệt bài viết"),
            ("WITHDRAW_REVIEW", "Rút gửi duyệt"),
            ("REOPEN", "Mở lại bài viết"),
            ("CANCEL", "Hủy bài viết"),
        ],
        verbose_name="Loại quyết định",
    )
    return_stage = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Công đoạn trả về",
    )
    reason = models.TextField(
        max_length=2000,
        blank=True,
        default="",
        verbose_name="Lý do / Hướng dẫn sửa",
    )
    checklist = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Checklist kiểm tra biên tập",
    )
    actor_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="review_decisions",
        verbose_name="Người đưa ra quyết định",
    )
    idempotency_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        verbose_name="Khóa chống trùng lặp (Idempotency Key)",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm quyết định")

    class Meta:
        verbose_name = "Quyết định biên tập"
        verbose_name_plural = "Quyết định biên tập"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["item", "created_at"], name="idx_decision_item_created"),
            models.Index(fields=["workspace", "created_at"], name="idx_decision_ws_created"),
        ]

    def __str__(self) -> str:
        return f"{self.item.title} - {self.get_decision_display()} ({self.created_at.strftime('%d/%m/%Y %H:%M')})"

    def save(self, *args, **kwargs):
        if not self._state.adding and ReviewDecision.objects.filter(pk=self.pk).exists():
            raise ValidationError("ReviewDecision là bản ghi append-only và không thể chỉnh sửa.")
        super().save(*args, **kwargs)


class ContentApproval(models.Model):
    """
    Bản ghi phê duyệt bài viết (Approval) - Spec mục 6.1, 6.3, 9, 13 B06:
    - Trỏ version_id cố định được Chủ duyệt.
    - Ghi nhận người duyệt (approved_by), thời điểm duyệt (approved_at).
    - Quản lý hiệu lực: invalidated_at, invalidation_reason khi mở lại bài (REOPENED).
    - Mỗi bài viết tối đa một approval có hiệu lực (invalidated_at__isnull=True).
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
        related_name="content_approvals",
        verbose_name="Workspace",
    )
    item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="approvals",
        verbose_name="Bài viết",
    )
    version = models.ForeignKey(
        ContentVersion,
        on_delete=models.PROTECT,
        related_name="approvals",
        verbose_name="Phiên bản nội dung được duyệt",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_contents",
        verbose_name="Chủ workspace duyệt",
    )
    approved_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm duyệt")
    invalidated_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm vô hiệu hóa")
    invalidation_reason = models.TextField(blank=True, default="", max_length=2000, verbose_name="Lý do vô hiệu hóa")
    idempotency_key = models.CharField(max_length=128, blank=True, default="", verbose_name="Khóa Idempotency")

    class Meta:
        verbose_name = "Bản ghi phê duyệt nội dung"
        verbose_name_plural = "Bản ghi phê duyệt nội dung"
        ordering = ["-approved_at"]
        indexes = [
            models.Index(fields=["item", "invalidated_at"], name="idx_appr_item_inval"),
            models.Index(fields=["workspace", "approved_at"], name="idx_appr_ws_approved"),
        ]

    @property
    def is_active(self) -> bool:
        return self.invalidated_at is None

    def __str__(self) -> str:
        status_str = "Hợp lệ" if self.is_active else f"Vô hiệu ({self.invalidated_at.strftime('%d/%m/%Y')})"
        return f"Duyệt {self.item.title} - v{self.version.version_no} [{status_str}]"

class Task(models.Model):
    """
    Nhiệm vụ tác nghiệp (Task) - Spec mục 6.2, 9, 13:
    - 3 nhiệm vụ trên mỗi bài: WRITE, EDIT, PUBLISH.
    - Sinh tự động khi Chủ duyệt kế hoạch (F02).
    - Ràng buộc: unique(item, role).
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
        related_name="tasks",
        verbose_name="Workspace",
    )
    item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Bài viết",
    )
    role = models.CharField(
        max_length=20,
        choices=TaskRole.choices,
        verbose_name="Vai trò nhiệm vụ",
    )
    assignee_membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Thành viên chịu trách nhiệm",
    )
    execution_mode = models.CharField(
        max_length=20,
        choices=TaskExecutionMode.choices,
        default=TaskExecutionMode.MANUAL,
        verbose_name="Hình thức thực hiện",
    )
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.WAITING,
        verbose_name="Trạng thái nhiệm vụ",
    )
    due_at = models.DateTimeField(
        verbose_name="Thời hạn nhiệm vụ",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời điểm cập nhật")

    class Meta:
        verbose_name = "Nhiệm vụ"
        verbose_name_plural = "Nhiệm vụ"
        ordering = ["due_at", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "role"],
                name="unique_item_task_role",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace", "assignee_membership", "status"], name="idx_task_ws_assignee_st"),
        ]

    def __str__(self) -> str:
        return f"{self.get_role_display()} - {self.item.title} [{self.get_status_display()}]"

    def clean(self) -> None:
        super().clean()
        if self.item_id and self.workspace_id and self.item.workspace_id != self.workspace_id:
            raise ValidationError({"item": "Bài viết không thuộc cùng workspace với nhiệm vụ."})
        if self.assignee_membership_id and self.workspace_id:
            if self.assignee_membership.workspace_id != self.workspace_id:
                raise ValidationError({"assignee_membership": "Thành viên được giao việc phải thuộc cùng workspace."})



