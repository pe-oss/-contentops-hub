from django.conf import settings


def billing_context(request):
    """Cung cấp trạng thái BILLING_ENABLED cho tất cả templates."""
    return {
        "BILLING_ENABLED": getattr(settings, "BILLING_ENABLED", False),
    }
