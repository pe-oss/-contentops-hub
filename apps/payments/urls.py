from django.urls import path

from .views import checkout_detail, checkout_status, create_checkout_order, payos_webhook, sepay_webhook

app_name = "payments"

urlpatterns = [
    path("checkout/<int:order_id>/status/", checkout_status, name="checkout_status"),
    path("checkout/<int:order_id>/", checkout_detail, name="checkout_detail"),
    path("checkout/<str:plan_type>/", create_checkout_order, name="checkout_create"),
    path("webhook/payos/", payos_webhook, name="payos_webhook"),
    path("webhook/sepay/", sepay_webhook, name="sepay_webhook"),
    # Backward-compatible aliases for previous boilerplate URLs.
    path("webhooks/payos/", payos_webhook, name="payos_webhook"),
    path("webhooks/sepay/", sepay_webhook, name="sepay_webhook"),
]