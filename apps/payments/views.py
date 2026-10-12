import hashlib
import hmac
import json
import secrets
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.payments.models import Order, PaymentHistory
from apps.payments.services.webhooks import process_payment_webhook


def _format_vnd(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".")


def _user_has_pro(user) -> bool:
    if not user.is_authenticated:
        return False
    return PaymentHistory.objects.filter(
        user=user,
        plan=PaymentHistory.Plan.PRO,
        status=PaymentHistory.Status.PAID,
    ).exists()


def _generate_order_code() -> str:
    today = timezone.localtime(timezone.now()).strftime("%y%m%d")
    while True:
        code = f"ORDER-{today}-{secrets.token_hex(2).upper()}"
        if not Order.objects.filter(order_code=code).exists():
            return code


def _build_vietqr_url(order: Order) -> str:
    if not settings.VIETQR_BANK_ID or not settings.VIETQR_ACCOUNT_NO:
        return ""
    base_url = f"https://img.vietqr.io/image/{settings.VIETQR_BANK_ID}-{settings.VIETQR_ACCOUNT_NO}-compact2.png"
    query_params = f"amount={order.amount}&addInfo={quote(order.order_code)}"
    if settings.VIETQR_ACCOUNT_NAME:
        query_params += f"&accountName={quote(settings.VIETQR_ACCOUNT_NAME)}"
    return f"{base_url}?{query_params}"


@require_GET
def pricing_view(request: HttpRequest):
    is_pro = _user_has_pro(request.user)
    context = {
        "is_pro": is_pro,
        "pro_price": settings.PRO_PLAN_PRICE,
        "pro_price_display": _format_vnd(settings.PRO_PLAN_PRICE),
    }
    return render(request, "payments/pricing.html", context)


@login_required
@require_POST
def create_checkout_order(request: HttpRequest, plan_type: str):
    plan_type = plan_type.lower()
    if plan_type != PaymentHistory.Plan.PRO:
        messages.error(request, "Gói dịch vụ không hợp lệ.")
        return redirect("pricing")

    if _user_has_pro(request.user):
        messages.info(request, "Tài khoản của bạn đã kích hoạt gói Pro.")
        return redirect("dashboard")

    order = Order.objects.create(
        user=request.user,
        order_code=_generate_order_code(),
        plan=PaymentHistory.Plan.PRO,
        amount=settings.PRO_PLAN_PRICE,
        status=Order.Status.PENDING,
    )
    messages.success(request, "Đơn thanh toán đã được tạo. Vui lòng chuyển khoản đúng nội dung để kích hoạt tự động.")
    return redirect("payments:checkout_detail", order_id=order.id)


@login_required
@require_GET
def checkout_detail(request: HttpRequest, order_id: int):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == Order.Status.PAID:
        messages.success(request, "Đơn hàng đã thanh toán. Gói Pro đã được kích hoạt.")
        return redirect("dashboard")

    context = {
        "order": order,
        "amount_display": _format_vnd(order.amount),
        "vietqr_url": _build_vietqr_url(order),
        "bank_id": settings.VIETQR_BANK_ID,
        "account_no": settings.VIETQR_ACCOUNT_NO,
        "account_name": settings.VIETQR_ACCOUNT_NAME,
        "status_url": reverse("payments:checkout_status", kwargs={"order_id": order.id}),
    }
    return render(request, "payments/checkout_detail.html", context)


@login_required
@require_GET
def checkout_status(request: HttpRequest, order_id: int) -> JsonResponse:
    order = get_object_or_404(Order, id=order_id, user=request.user)
    paid = order.status == Order.Status.PAID
    return JsonResponse(
        {
            "status": order.status,
            "status_display": order.get_status_display(),
            "paid": paid,
            "redirect_url": reverse("dashboard") if paid else "",
        }
    )


def _json_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"status": "error", "message": message}, status=status)


def _parse_json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_json") from exc


def _verify_payos_signature(payload: bytes, signature: str | None) -> bool:
    secret = settings.PAYOS_WEBHOOK_SECRET
    if not secret:
        return True
    if not signature:
        return False
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_sepay_secret(request: HttpRequest) -> bool:
    secret = settings.SEPAY_WEBHOOK_SECRET
    if not secret:
        return True
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif authorization.lower().startswith("apikey "):
        token = authorization[7:].strip()
    else:
        token = authorization.strip()
    
    provided = token or request.headers.get("x-sepay-secret") or request.headers.get("x-webhook-secret")
    return hmac.compare_digest(provided or "", secret)


def _handle_payment_webhook(request: HttpRequest, gateway: str) -> JsonResponse:
    try:
        payload = _parse_json_body(request)
        status, _order = process_payment_webhook(gateway, payload)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("webhook_processing_failed", 500)

    if status == "duplicate":
        return JsonResponse({"success": True, "status": "success", "idempotent": True})
    return JsonResponse({"success": True, "status": "success"})


@csrf_exempt
@require_POST
def payos_webhook(request: HttpRequest) -> JsonResponse:
    signature = request.headers.get("x-payos-signature") or request.headers.get("signature")
    if not _verify_payos_signature(request.body, signature):
        return _json_error("invalid_signature", 401)
    return _handle_payment_webhook(request, PaymentHistory.Provider.PAYOS)


@csrf_exempt
@require_POST
def sepay_webhook(request: HttpRequest) -> JsonResponse:
    if not _verify_sepay_secret(request):
        return _json_error("invalid_authorization", 401)
    return _handle_payment_webhook(request, PaymentHistory.Provider.SEPAY)