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

