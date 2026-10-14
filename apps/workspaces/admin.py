from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import AccessRole, Membership, MembershipStatus, Workspace


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    readonly_fields = ("id", "created_at", "updated_at")
    fields = ("user", "access_role", "employment_type", "status", "ai_use_allowed", "created_at")


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "id", "owner_user", "timezone", "created_at")
    list_filter = ("timezone", "created_at")
    search_fields = ("name", "owner_user__username", "owner_user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [MembershipInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Đảm bảo sau khi lưu workspace qua admin, owner_user luôn có membership OWNER tương ứng
        membership, created = Membership.objects.get_or_create(
            workspace=obj,
            user=obj.owner_user,
            defaults={
                "access_role": AccessRole.OWNER,
                "status": MembershipStatus.ACTIVE,
                "ai_use_allowed": True,
            },
        )
        if not created and membership.access_role != AccessRole.OWNER:
            membership.access_role = AccessRole.OWNER
            membership.status = MembershipStatus.ACTIVE
            membership.save(update_fields=["access_role", "status", "updated_at"])


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = (
        "workspace",
        "user",
        "access_role",
        "employment_type",
        "status",
        "ai_use_allowed",
        "created_at",
    )
    list_filter = ("access_role", "employment_type", "status", "ai_use_allowed")
    search_fields = ("workspace__name", "user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        # Đảm bảo tính nhất quán: Nếu gán role OWNER, phải đồng bộ với workspace.owner_user
        if obj.access_role == AccessRole.OWNER:
            if obj.workspace.owner_user_id != obj.user_id:
                # Mỗi workspace chỉ có một Chủ, chuyển owner_user của workspace hoặc từ chối
                # Theo nguyên tắc B01: owner_user là nguồn xác định Chủ; membership OWNER phải nhất quán.
                # Kiểm tra xem có membership OWNER nào khác không:
                other_owner = (
                    Membership.objects.filter(workspace=obj.workspace, access_role=AccessRole.OWNER)
                    .exclude(pk=obj.pk)
                    .exists()
                )
                if other_owner:
                    raise ValidationError("Mỗi workspace chỉ có duy nhất một Chủ (OWNER).")
                obj.workspace.owner_user = obj.user
                obj.workspace.save(update_fields=["owner_user", "updated_at"])
        elif obj.workspace.owner_user_id == obj.user_id:
            # Không thể hạ quyền OWNER của người đang là workspace.owner_user
            raise ValidationError("Không thể chuyển vai trò của Chủ workspace sang vai trò khác.")

        super().save_model(request, obj, form, change)


from .models import Invitation


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "workspace",
        "access_role",
        "employment_type",
        "invited_by",
        "expires_at",
        "accepted_at",
        "revoked_at",
        "created_at",
    )
    list_filter = ("access_role", "employment_type", "created_at")
    search_fields = ("email", "workspace__name", "invited_by__username")
    readonly_fields = ("id", "token_hash", "created_at", "updated_at", "accepted_at", "revoked_at", "last_sent_at")

    def save_model(self, request, obj, form, change):
        if obj.access_role == AccessRole.OWNER:
            raise ValidationError("Không thể tạo lời mời cho vai trò OWNER.")
        super().save_model(request, obj, form, change)



from .models import BrandProfile


@admin.register(BrandProfile)
class BrandProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "revision", "updated_by", "updated_at")
    list_filter = ("revision", "updated_at")
    search_fields = ("name", "workspace__name", "product_summary")
    readonly_fields = ("id", "revision", "created_at", "updated_at")
from .models import ContentApproval, ContentItem, ContentPublication, ContentVersion, Package, PlanApproval, ReviewDecision, Task


class ContentItemInline(admin.TabularInline):
    model = ContentItem
    extra = 0
    readonly_fields = ("id", "state", "row_version", "created_at")
    fields = ("title", "state", "writer_membership", "editor_membership", "publisher_membership", "writing_deadline", "planned_publish_at")


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "status", "coordinator_membership", "plan_revision", "row_version", "start_date", "end_date", "created_at")
    list_filter = ("status", "channel", "created_at")
    search_fields = ("name", "workspace__name", "objective")
    readonly_fields = ("id", "plan_revision", "row_version", "brand_snapshot", "created_at", "updated_at")
    inlines = [ContentItemInline]


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("title", "package", "workspace", "state", "writer_membership", "editor_membership", "publisher_membership", "row_version")
    list_filter = ("state", "created_at")
    search_fields = ("title", "brief", "package__name", "workspace__name")
    readonly_fields = ("id", "row_version", "created_at", "updated_at")


@admin.register(PlanApproval)
class PlanApprovalAdmin(admin.ModelAdmin):
    list_display = ("package", "plan_revision", "owner", "approved_at", "idempotency_key")
    list_filter = ("plan_revision", "approved_at")
    search_fields = ("package__name", "owner__username")
    readonly_fields = ("id", "plan_revision", "immutable_plan_snapshot", "approved_at")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("item", "role", "assignee_membership", "status", "due_at")
    list_filter = ("role", "status", "due_at")
    search_fields = ("item__title", "assignee_membership__user__username")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display = ("item", "version_no", "source", "author_membership", "created_at")
    list_filter = ("source", "created_at")
    search_fields = ("item__title", "author_membership__user__username", "text")
    readonly_fields = ("id", "version_no", "text", "reference_urls", "source", "author_membership", "parent_version", "created_at")


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(admin.ModelAdmin):
    list_display = ("item", "decision", "version", "actor_membership", "created_at")
    list_filter = ("decision", "created_at")
    search_fields = ("item__title", "actor_membership__user__username", "reason")
    readonly_fields = ("id", "item", "version", "decision", "return_stage", "reason", "checklist", "actor_membership", "created_at")


@admin.register(ContentApproval)
class ContentApprovalAdmin(admin.ModelAdmin):
    list_display = ("item", "version", "approved_by", "approved_at", "invalidated_at")
    list_filter = ("approved_at", "invalidated_at")
    search_fields = ("item__title", "approved_by__username", "invalidation_reason")
    readonly_fields = ("id", "workspace", "item", "version", "approved_by", "approved_at", "invalidated_at", "invalidation_reason", "idempotency_key")


@admin.register(ContentPublication)
class ContentPublicationAdmin(admin.ModelAdmin):
    list_display = ("item", "version", "url", "published_at", "recorded_by", "recorded_at")
    list_filter = ("published_at", "recorded_at")
    search_fields = ("item__title", "url", "recorded_by__username")
    readonly_fields = ("id", "workspace", "item", "version", "approval", "recorded_at")

