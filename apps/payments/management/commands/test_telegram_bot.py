import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Gửi tin nhắn test để kiểm tra kết nối Telegram Bot từ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID trong .env."

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID

        if not token:
            raise CommandError("Thiếu TELEGRAM_BOT_TOKEN trong file .env.")
        if not chat_id:
            raise CommandError("Thiếu TELEGRAM_CHAT_ID trong file .env.")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "🔔 Kiểm tra kết nối Telegram Bot thành công!",
        }

        try:
            response = requests.post(url, json=payload, timeout=15)
        except requests.RequestException as exc:
            raise CommandError(f"Không thể kết nối Telegram API: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            data = {"raw_response": response.text}

        if response.status_code == 200 and data.get("ok") is True:
            self.stdout.write(self.style.SUCCESS("Telegram test OK: HTTP 200 - Đã gửi tin nhắn test thành công."))
            return

        description = data.get("description") or data.get("raw_response") or "Không có mô tả lỗi từ Telegram."
        self.stdout.write(self.style.ERROR(f"Telegram test FAILED: HTTP {response.status_code}"))
        self.stdout.write(self.style.ERROR(f"Telegram response: {data}"))

        hint = ""
        lowered = str(description).lower()
        if response.status_code == 401 or "unauthorized" in lowered:
            hint = "Bot token không hợp lệ. Hãy kiểm tra TELEGRAM_BOT_TOKEN lấy từ @BotFather, tránh thừa dấu cách/ký tự xuống dòng."
        elif "chat not found" in lowered:
            hint = "Chat ID không đúng hoặc bot chưa có quyền trong chat. Hãy nhắn /start cho bot nếu là chat cá nhân; nếu là group/channel hãy thêm bot vào và dùng đúng chat_id."
        elif response.status_code == 400 or "bad request" in lowered:
            hint = "Bad Request. Thường do TELEGRAM_CHAT_ID sai định dạng, bot chưa được thêm vào group/channel, hoặc payload không hợp lệ."
        elif response.status_code == 403 or "forbidden" in lowered:
            hint = "Bot bị chặn hoặc không có quyền gửi tin nhắn vào chat này. Hãy unblock bot hoặc cấp quyền gửi tin trong group/channel."
        elif response.status_code == 429:
            hint = "Telegram rate limit. Hãy chờ một lúc rồi thử lại."

        if hint:
            self.stdout.write(self.style.WARNING(f"Gợi ý khắc phục: {hint}"))

        raise CommandError(f"Gửi Telegram test thất bại: {description}")