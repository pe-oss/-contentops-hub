import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _escape_markdown(value: object) -> str:
    text = str(value or "-")
    for char in "_*[]()~`>#+-=|{}.!":
        text = text.replace(char, f"\\{char}")
    return text


def send_telegram_payment_notification(order, transaction_data: dict) -> bool:
    if not getattr(settings, "BILLING_ENABLED", False):
        logger.info("Telegram notification skipped: BILLING_ENABLED is False.")
        return False
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.info("Telegram payment notification skipped because bot token/chat id is not configured.")
        return False

    try:
        user = order.user
        customer = user.get_full_name() or user.username or user.email
        paid_at = order.paid_at or timezone.now()
        amount = f"{int(order.amount):,}".replace(",", ".")
        gateway = transaction_data.get("gateway") or transaction_data.get("provider") or "-"
        transaction_id = transaction_data.get("transaction_id") or transaction_data.get("reference") or "-"

        message = "\n".join([
            "✅ *Thanh toán thành công*",
            "",
            f"👤 *Khách hàng:* {_escape_markdown(customer)}",
            f"📧 *Email:* {_escape_markdown(user.email)}",
            f"📦 *Gói dịch vụ:* {_escape_markdown(order.get_plan_display())}",
            f"💰 *Số tiền:* `{amount} VND`",
            f"🏦 *Mã giao dịch:* `{_escape_markdown(transaction_id)}`",
            f"🌐 *Cổng thanh toán:* {_escape_markdown(str(gateway).upper())}",
            f"🕒 *Thời gian:* {_escape_markdown(timezone.localtime(paid_at).strftime('%d/%m/%Y %H:%M:%S'))}",
        ])

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "MarkdownV2"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send Telegram payment notification.")
        return False