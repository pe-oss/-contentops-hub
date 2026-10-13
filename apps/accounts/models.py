from django.conf import settings
from django.db import models
from django.utils import timezone


class AccountEmailIdentity(models.Model):
    """Lưu trữ định danh email chuẩn hóa và trạng thái xác minh của người dùng."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_identity",
    )
    normalized_email = models.EmailField(
        max_length=254,
        unique=True,
        db_index=True,
        verbose_name="Email đã chuẩn hóa",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời điểm xác minh",
    )
    last_verification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Thời điểm gửi mã xác minh gần nhất",
    )
    token_version = models.PositiveIntegerField(
        default=1,
        verbose_name="Phiên bản token xác minh",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Định danh Email"
        verbose_name_plural = "Định danh Email"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.normalized_email} ({'Verified' if self.is_verified else 'Unverified'})"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    def mark_as_verified(self):
        self.verified_at = timezone.now()
        self.save(update_fields=["verified_at", "updated_at"])

    def reset_verification(self):
        self.verified_at = None
        self.save(update_fields=["verified_at", "updated_at"])
