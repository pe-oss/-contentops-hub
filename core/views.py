from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.payments.models import PaymentHistory


@login_required
def dashboard(request):
    payments = PaymentHistory.objects.filter(user=request.user)
    has_pro_payment = payments.filter(
        plan=PaymentHistory.Plan.PRO,
        status=PaymentHistory.Status.PAID,
    ).exists()

    context = {
        "subscription_status": "Pro" if has_pro_payment else "Free",
        "payments": payments[:10],
    }
    return render(request, "dashboard.html", context)