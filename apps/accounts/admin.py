from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AccountEmailIdentity

User = get_user_model()


class AccountEmailIdentityInline(admin.StackedInline):
    model = AccountEmailIdentity
    can_delete = False
    verbose_name_plural = "Định danh Email"
    fields = ("normalized_email", "verified_at", "last_verification_sent_at")
    readonly_fields = ("last_verification_sent_at",)


class CustomUserAdmin(BaseUserAdmin):
    inlines = (AccountEmailIdentityInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(AccountEmailIdentity)
class AccountEmailIdentityAdmin(admin.ModelAdmin):
    list_display = ("normalized_email", "user", "verified_at", "is_verified", "created_at")
    list_filter = ("verified_at", "created_at")
    search_fields = ("normalized_email", "user__username")
    readonly_fields = ("created_at", "updated_at", "last_verification_sent_at")
