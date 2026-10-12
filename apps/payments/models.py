from django.conf import settings
from django.db import models


class PaymentHistory(models.Model):
    class Provider(models.TextChoices):
        PAYOS = "payos", "PayOS"
        SEPAY = "sepay", "SePay"

    class Status(models.TextChoices):
        PENDING = "pending", "Đang chờ"
        PAID = "paid", "Đã thanh toán"
        FAILED = "failed", "Thất bại"

    class Plan(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_histories",
        null=True,
        blank=True,
    )
    transaction_id = models.CharField(max_length=120, unique=True, null=True, blank=True)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    order_code = models.CharField(max_length=100, blank=True)
    amount = models.PositiveIntegerField(default=0)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lịch sử thanh toán"
        verbose_name_plural = "Lịch sử thanh toán"

    def __str__(self) -> str:
        return f"{self.get_provider_display()} - {self.order_code or self.pk} - {self.get_status_display()}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Đang chờ"
        PAID = "paid", "Đã thanh toán"
        FAILED = "failed", "Thất bại"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    order_code = models.CharField(max_length=100, unique=True)
    plan = models.CharField(max_length=20, choices=PaymentHistory.Plan.choices, default=PaymentHistory.Plan.PRO)
    amount = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order_code} - {self.user} - {self.get_status_display()}"