from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import AccountEmailIdentity
from .services import normalize_email

User = get_user_model()


class AccountEmailIdentityInline(admin.StackedInline):
    model = AccountEmailIdentity
    can_delete = False
    verbose_name_plural = "Định danh Email"
    fields = ("normalized_email", "token_version", "verified_at", "last_verification_sent_at")
    readonly_fields = ("token_version", "last_verification_sent_at")


class CustomUserAdmin(BaseUserAdmin):
    inlines = (AccountEmailIdentityInline,)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if obj.email:
            norm_email = normalize_email(obj.email)
            # Kiểm tra trùng email với tài khoản khác
            conflict = AccountEmailIdentity.objects.exclude(user=obj).filter(normalized_email=norm_email).exists()
            if conflict:
                raise ValidationError(f"Email '{norm_email}' đã được sử dụng bởi một tài khoản khác.")
            obj.email = norm_email

        super().save_model(request, obj, form, change)

        if obj.email:
            norm_email = normalize_email(obj.email)
            identity, created = AccountEmailIdentity.objects.select_for_update().get_or_create(
                user=obj,
                defaults={"normalized_email": norm_email, "verified_at": None, "token_version": 1},
            )
            if not created and identity.normalized_email != norm_email:
                # Đổi email qua admin: cập nhật và reset verified_at, tăng token_version
                identity.normalized_email = norm_email
                identity.reset_verification()
                identity.token_version += 1
                identity.save(update_fields=["normalized_email", "verified_at", "token_version", "updated_at"])


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(AccountEmailIdentity)
class AccountEmailIdentityAdmin(admin.ModelAdmin):
    list_display = ("normalized_email", "user", "token_version", "verified_at", "is_verified", "created_at")
    list_filter = ("verified_at", "created_at")
    search_fields = ("normalized_email", "user__username")
    readonly_fields = ("token_version", "created_at", "updated_at", "last_verification_sent_at")
