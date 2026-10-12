from django.contrib import admin

from .models import Order, PaymentHistory


@admin.register(PaymentHistory)
class PaymentHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "provider", "transaction_id", "order_code", "amount", "plan", "status", "created_at")
    list_filter = ("provider", "plan", "status", "created_at")
    search_fields = ("transaction_id", "order_code", "user__username", "user__email")
    readonly_fields = ("created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "order_code", "plan", "amount", "status", "paid_at", "created_at")
    list_filter = ("plan", "status", "created_at", "paid_at")
    search_fields = ("order_code", "user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")