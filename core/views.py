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


# ==============================================================================
# B10 Custom Error Handlers (Zero Leakage, Safe Context)
# ==============================================================================

def custom_bad_request_view(request, exception=None):
    """Xử lý lỗi 400 Bad Request."""
    return render(request, "400.html", status=400)


def custom_permission_denied_view(request, exception=None):
    """Xử lý lỗi 403 Forbidden / Permission Denied."""
    return render(request, "403.html", status=403)


def custom_page_not_found_view(request, exception=None):
    """Xử lý lỗi 404 Not Found."""
    return render(request, "404.html", status=404)


def custom_server_error_view(request):
    """Xử lý lỗi 500 Internal Server Error (Không lộ traceback hay secret)."""
    return render(request, "500.html", status=500)


def custom_csrf_failure_view(request, reason=""):
    """Xử lý lỗi CSRF 403 Forbidden với hướng dẫn rõ ràng cho người dùng."""
    return render(request, "403_csrf.html", status=403)
def test_auto_login(request, user_id):
    """Tiện ích đăng nhập nhanh dành cho kiểm thử trình duyệt tự động (chỉ bật khi DEBUG hoặc TEST_MODE)."""
    if not (settings.DEBUG or getattr(settings, "TEST_MODE", False)):
        from django.http import Http404
        raise Http404()
    from django.contrib.auth import get_user_model, login
    from django.shortcuts import redirect
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        login(request, user)
        next_url = request.GET.get("next", "/")
        return redirect(next_url)
    except User.DoesNotExist:
        from django.http import Http404
        raise Http404()
def test_trigger_error(request, code):
    """Tiện ích kích hoạt render trang lỗi dành cho chụp bằng chứng kiểm thử."""
    if not (settings.DEBUG or getattr(settings, "TEST_MODE", False)):
        from django.http import Http404
        raise Http404()
    if code == 400:
        return custom_bad_request_view(request)
    elif code == 403:
        return custom_permission_denied_view(request)
    elif code == 404:
        return custom_page_not_found_view(request)
    elif code == 409:
        return render(request, "409.html", {"error_message": "Xung đột phiên bản: Bài viết đã được duyệt ở phiên khác."}, status=409)
    elif code == 500:
        return custom_server_error_view(request)
    from django.http import Http404
    raise Http404()



