import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.payments.models import PaymentHistory
from apps.payments.services.webhooks import process_payment_webhook


class Command(BaseCommand):
    help = "Giả lập webhook thanh toán PayOS/SePay để test kích hoạt tài khoản và Telegram."

    def add_arguments(self, parser):
        parser.add_argument("--gateway", choices=[PaymentHistory.Provider.PAYOS, PaymentHistory.Provider.SEPAY], required=True)
        parser.add_argument("--amount", type=int, required=True)
        parser.add_argument("--username", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--plan", choices=PaymentHistory.Plan.values, default=PaymentHistory.Plan.PRO)
        parser.add_argument("--order-code", default="")
        parser.add_argument("--transaction-id", default="")

    def handle(self, *args, **options):
        User = get_user_model()
        user = None
        if options["username"]:
            user = User.objects.filter(username__iexact=options["username"]).first()
        if user is None and options["email"]:
            user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            user = User.objects.order_by("id").first()
        if user is None:
            raise CommandError("Không có user nào để kích hoạt. Hãy tạo user trước hoặc truyền --username/--email.")

        transaction_id = options["transaction_id"] or f"MOCK-{options['gateway'].upper()}-{uuid.uuid4().hex[:12]}"
        order_code = options["order_code"] or f"ORDER-{uuid.uuid4().hex[:10].upper()}"
        payload = {
            "transaction_id": transaction_id,
            "order_code": order_code,
            "amount": options["amount"],
            "plan": options["plan"],
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "mock": True,
        }

        status, order = process_payment_webhook(options["gateway"], payload)
        self.stdout.write(self.style.SUCCESS(f"Mock webhook processed: status={status}, order={order.order_code if order else '-'}, user={user.username}"))