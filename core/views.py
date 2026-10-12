from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.payments.models import PaymentHistory


@login_required
def dashboard(request):
    billing_enabled = getattr(settings, "BILLING_ENABLED", False)
    if billing_enabled:
        payments = PaymentHistory.objects.filter(user=request.user)
        has_pro_payment = payments.filter(
            plan=PaymentHistory.Plan.PRO,
            status=PaymentHistory.Status.PAID,
        ).exists()
        subscription_status = "Pro" if has_pro_payment else "Free"
        recent_payments = payments[:10]
    else:
        subscription_status = None
        recent_payments = []

    context = {
        "subscription_status": subscription_status,
        "payments": recent_payments,
        "billing_enabled": billing_enabled,
    }
    return render(request, "dashboard.html", context)
