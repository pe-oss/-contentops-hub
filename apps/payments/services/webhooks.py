from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.payments.models import Order, PaymentHistory
from apps.payments.services.telegram import send_telegram_payment_notification


@dataclass(frozen=True)
class NormalizedPayment:
    gateway: str
    transaction_id: str
    order_code: str
    amount: int
    plan: str
    user_lookup: str
    raw_payload: dict


def _first_value(data: dict, keys: tuple[str, ...], default=""):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def normalize_payment_payload(gateway: str, payload: dict) -> NormalizedPayment:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    transaction_id = str(_first_value(data, ("transaction_id", "transactionId", "reference", "referenceCode", "id", "code")))
    order_code = str(_first_value(data, ("order_code", "orderCode", "order_id", "orderId", "content", "description"), transaction_id))
    amount = int(_first_value(data, ("amount", "transferAmount", "value"), 0) or 0)
    plan = str(_first_value(data, ("plan", "package", "subscription"), PaymentHistory.Plan.PRO)).lower()
    if plan not in PaymentHistory.Plan.values:
        plan = PaymentHistory.Plan.PRO
    user_lookup = str(_first_value(data, ("user_id", "userId", "username", "email", "customer_email", "customerEmail")))

    return NormalizedPayment(gateway, transaction_id, order_code, amount, plan, user_lookup, payload)


def _resolve_user(user_lookup: str):
    User = get_user_model()
    if not user_lookup:
        return User.objects.order_by("id").first()
    if user_lookup.isdigit():
        user = User.objects.filter(id=int(user_lookup)).first()
        if user:
            return user
    return User.objects.filter(username__iexact=user_lookup).first() or User.objects.filter(email__iexact=user_lookup).first()


def process_payment_webhook(gateway: str, payload: dict) -> tuple[str, Order | None]:
    normalized = normalize_payment_payload(gateway, payload)
    if not normalized.transaction_id:
        raise ValueError("missing_transaction_id")
    if not normalized.order_code:
        raise ValueError("missing_order_code")

    with transaction.atomic():
        existing_payment = PaymentHistory.objects.select_related("user").filter(transaction_id=normalized.transaction_id).first()
        if existing_payment:
            order = Order.objects.filter(order_code=existing_payment.order_code).select_related("user").first()
            return "duplicate", order

        user = _resolve_user(normalized.user_lookup)
        if user is None:
            raise ValueError("user_not_found")

        order, _ = Order.objects.select_for_update().get_or_create(
            order_code=normalized.order_code,
            defaults={"user": user, "plan": normalized.plan, "amount": normalized.amount, "status": Order.Status.PENDING},
        )
        order.user = order.user or user
        order.plan = normalized.plan or order.plan
        order.amount = normalized.amount or order.amount
        order.status = Order.Status.PAID
        order.paid_at = order.paid_at or timezone.now()
        order.save(update_fields=["user", "plan", "amount", "status", "paid_at", "updated_at"])

        PaymentHistory.objects.create(
            user=order.user,
            transaction_id=normalized.transaction_id,
            provider=gateway,
            order_code=order.order_code,
            amount=order.amount,
            plan=order.plan,
            status=PaymentHistory.Status.PAID,
            raw_payload=normalized.raw_payload,
        )

        transaction.on_commit(lambda: send_telegram_payment_notification(order, {"gateway": gateway, "transaction_id": normalized.transaction_id, "payload": normalized.raw_payload}))
        return "success", order