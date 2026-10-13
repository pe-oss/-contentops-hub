import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import AccountEmailIdentity

logger = logging.getLogger(__name__)
User = get_user_model()
RESEND_COOLDOWN_SECONDS = 60


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """
    Sinh token xác minh dùng một lần (single-use verification token).
    Băm gồm: user.pk, password hash, timestamp, email, token_version, verified_at.
    Bất kỳ thay đổi nào về mật khẩu, email, hoặc token_version đều làm mất hiệu lực token cũ.
    """

    def _make_hash_value(self, user, timestamp):
        email_str = user.email or ""
        token_ver = 1
        verified_str = ""
        if hasattr(user, "email_identity") and user.email_identity:
            token_ver = getattr(user.email_identity, "token_version", 1)
            if user.email_identity.verified_at:
                verified_str = user.email_identity.verified_at.isoformat()
        return f"{user.pk}{user.password}{timestamp}{email_str}{token_ver}{verified_str}"


email_verification_token_generator = EmailVerificationTokenGenerator()


def normalize_email(email: str) -> str:
    return email.strip().lower() if email else ""


def get_identity_by_email(email: str) -> AccountEmailIdentity | None:
    norm = normalize_email(email)
    if not norm:
        return None
    return AccountEmailIdentity.objects.filter(normalized_email=norm).select_related("user").first()


@transaction.atomic
def create_user_with_identity(
    *,
    username: str,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    send_email: bool = True,
    request=None,
) -> User:
    """
    Tạo User và AccountEmailIdentity trong cùng transaction.
    Chỉ gửi email sau khi transaction commit thành công.
    Lỗi gửi email không làm rollback hoặc hủy tài khoản đã tạo hợp lệ.
    """
    norm = normalize_email(email)
    if not norm:
        raise ValidationError("Email không được để trống.")
    if AccountEmailIdentity.objects.filter(normalized_email=norm).exists():
        raise ValidationError("Email này đã được sử dụng bởi tài khoản khác.")

    user = User.objects.create_user(
        username=username.strip(),
        email=norm,
        password=password,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
    )
    # Signal post_save có thể đã tạo identity, get_or_create bảo đảm an toàn
    AccountEmailIdentity.objects.get_or_create(
        user=user,
        defaults={"normalized_email": norm, "verified_at": None, "token_version": 1},
    )

    if send_email:
        # Gửi email SAU KHI transaction commit thành công
        transaction.on_commit(lambda: send_verification_email(user, request=request))
    return user


@transaction.atomic
def update_user_email(
    user: User,
    new_email: str,
    send_email: bool = True,
    request=None,
) -> AccountEmailIdentity:
    """
    Cập nhật email cho user:
    - Khóa bản ghi (select_for_update) chống xung đột đồng thời.
    - Reset verified_at = None, tăng token_version để hủy toàn bộ token cũ.
    - Chỉ gửi email sau khi transaction commit thành công.
    """
    norm = normalize_email(new_email)
    if not norm:
        raise ValidationError("Email không được để trống.")

    identity, _ = AccountEmailIdentity.objects.select_for_update().get_or_create(
        user=user,
        defaults={"normalized_email": norm, "verified_at": None, "token_version": 1},
    )
    if identity.normalized_email == norm and identity.is_verified:
        return identity

    if AccountEmailIdentity.objects.exclude(user=user).filter(normalized_email=norm).exists():
        raise ValidationError("Email này đã được sử dụng bởi tài khoản khác.")

    user.email = norm
    user.save(update_fields=["email"])

    identity.normalized_email = norm
    identity.reset_verification()
    identity.token_version += 1
    identity.save(update_fields=["normalized_email", "verified_at", "token_version", "updated_at"])

    if send_email:
        transaction.on_commit(lambda: send_verification_email(user, request=request))
    return identity


def can_send_verification_email(identity: AccountEmailIdentity) -> tuple[bool, int]:
    if not identity.last_verification_sent_at:
        return True, 0
    elapsed = (timezone.now() - identity.last_verification_sent_at).total_seconds()
    if elapsed < RESEND_COOLDOWN_SECONDS:
        return False, int(RESEND_COOLDOWN_SECONDS - elapsed)
    return True, 0


def send_verification_email(user: User, request=None) -> tuple[bool, str]:
    """
    Gửi email xác minh.
    - Tuân thủ rate-limit cooldown.
    - Tuyệt đối không log token hoặc URL xác minh.
    - Nếu SMTP lỗi: không cập nhật last_verification_sent_at để tránh phạt cooldown oan.
    """
    identity, _ = AccountEmailIdentity.objects.get_or_create(
        user=user, defaults={"normalized_email": normalize_email(user.email)}
    )
    allowed, remaining = can_send_verification_email(identity)
    if not allowed:
        return False, f"Vui lòng đợi {remaining} giây trước khi gửi lại."

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token_generator.make_token(user)
    verify_path = reverse("accounts:verify_email", kwargs={"uidb64": uidb64, "token": token})

    if request:
        verify_url = request.build_absolute_uri(verify_path)
    else:
        domain = getattr(settings, "PRIMARY_DOMAIN", "localhost:8000")
        protocol = "https" if getattr(settings, "IS_PRODUCTION", False) else "http"
        verify_url = f"{protocol}://{domain}{verify_path}"

    subject = "Xác nhận địa chỉ email - ContentOps Hub"
    message = (
        f"Xin chào {user.first_name or user.username},\n\n"
        f"Nhấn vào liên kết sau để xác minh email:\n{verify_url}\n\n"
        f"Liên kết có hiệu lực trong 24 giờ và chỉ có giá trị sử dụng một lần.\n\n"
        f"ContentOps Hub"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@contentopshub.com")

    try:
        send_mail(subject, message, from_email, [identity.normalized_email], fail_silently=False)
    except Exception as exc:
        # Ghi log lỗi SMTP tổng quát, KHÔNG ghi token hay URL
        logger.warning(
            "Không thể gửi email xác minh cho user_id=%s do lỗi SMTP (%s)",
            user.pk,
            exc.__class__.__name__,
        )
        return False, "Không thể gửi email xác minh lúc này. Vui lòng thử lại sau."

    # Chỉ ghi nhận thời điểm gửi thành công để kích hoạt cooldown
    identity.last_verification_sent_at = timezone.now()
    identity.save(update_fields=["last_verification_sent_at", "updated_at"])
    return True, "Email xác minh đã được gửi thành công."


@transaction.atomic
def verify_email_token(uidb64: str, token: str) -> tuple[bool, str, User | None]:
    """
    Xác minh token kích hoạt email:
    - Khóa bản ghi (select_for_update) chống xử lý đồng thời.
    - Kiểm tra email hiện tại có khớp với token không.
    - Kiểm tra token dùng 1 lần: sau khi xác minh thành công, tăng token_version để vô hiệu hóa token ngay lập tức.
    - Không log token hoặc URL.
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False, "Liên kết xác minh không hợp lệ.", None

    try:
        identity = AccountEmailIdentity.objects.select_for_update().get(user=user)
    except AccountEmailIdentity.DoesNotExist:
        return False, "Không tìm thấy định danh email của tài khoản.", user

    # Nếu đã được xác minh trước đó
    if identity.is_verified:
        return False, "Địa chỉ email này đã được xác minh trước đó.", user

    # Đảm bảo email của identity khớp với email hiện tại của User
    if identity.normalized_email != normalize_email(user.email):
        return False, "Liên kết xác minh không khớp với email hiện tại của tài khoản.", user

    # Kiểm tra tính hợp lệ của token
    if not email_verification_token_generator.check_token(user, token):
        return False, "Liên kết xác minh không hợp lệ hoặc đã hết hạn.", user

    # Xác minh thành công: đánh dấu verified và tăng token_version để vô hiệu hóa token (dùng 1 lần duy nhất)
    identity.mark_as_verified()
    identity.token_version += 1
    identity.save(update_fields=["verified_at", "token_version", "updated_at"])

    return True, "Email của bạn đã được xác minh thành công!", user
