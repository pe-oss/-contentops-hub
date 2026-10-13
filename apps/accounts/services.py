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
    def _make_hash_value(self, user, timestamp):
        email_str = user.email or ""
        verified_str = ""
        if hasattr(user, "email_identity") and user.email_identity and user.email_identity.verified_at:
            verified_str = user.email_identity.verified_at.isoformat()
        return f"{user.pk}{user.password}{timestamp}{email_str}{verified_str}"


email_verification_token_generator = EmailVerificationTokenGenerator()


def normalize_email(email: str) -> str:
    return email.strip().lower() if email else ""


def get_identity_by_email(email: str) -> AccountEmailIdentity | None:
    norm = normalize_email(email)
    if not norm:
        return None
    return AccountEmailIdentity.objects.filter(normalized_email=norm).select_related("user").first()


@transaction.atomic
def create_user_with_identity(*, username, email, password, first_name="", last_name="", send_email=True, request=None) -> User:
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
    AccountEmailIdentity.objects.create(user=user, normalized_email=norm, verified_at=None)

    if send_email:
        try:
            send_verification_email(user, request=request)
        except Exception as exc:
            logger.warning("Không gửi được email xác minh: %s", exc)
    return user


@transaction.atomic
def update_user_email(user: User, new_email: str, send_email: bool = True, request=None) -> AccountEmailIdentity:
    norm = normalize_email(new_email)
    if not norm:
        raise ValidationError("Email không được để trống.")

    identity, _ = AccountEmailIdentity.objects.get_or_create(user=user, defaults={"normalized_email": norm})
    if identity.normalized_email == norm and identity.is_verified:
        return identity

    if AccountEmailIdentity.objects.exclude(user=user).filter(normalized_email=norm).exists():
        raise ValidationError("Email này đã được sử dụng bởi tài khoản khác.")

    user.email = norm
    user.save(update_fields=["email"])
    identity.normalized_email = norm
    identity.reset_verification()

    if send_email:
        try:
            send_verification_email(user, request=request)
        except Exception as exc:
            logger.warning("Không gửi được email xác minh: %s", exc)
    return identity


def can_send_verification_email(identity: AccountEmailIdentity) -> tuple[bool, int]:
    if not identity.last_verification_sent_at:
        return True, 0
    elapsed = (timezone.now() - identity.last_verification_sent_at).total_seconds()
    if elapsed < RESEND_COOLDOWN_SECONDS:
        return False, int(RESEND_COOLDOWN_SECONDS - elapsed)
    return True, 0


def send_verification_email(user: User, request=None) -> tuple[bool, str]:
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
    message = f"Xin chào {user.first_name or user.username},\n\nNhấn vào liên kết sau để xác minh email:\n{verify_url}\n\nLiên kết có hiệu lực trong 24 giờ.\n\nContentOps Hub"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@contentopshub.com")
    send_mail(subject, message, from_email, [identity.normalized_email], fail_silently=False)

    identity.last_verification_sent_at = timezone.now()
    identity.save(update_fields=["last_verification_sent_at", "updated_at"])
    return True, "Email xác minh đã được gửi thành công."


def verify_email_token(uidb64: str, token: str) -> tuple[bool, str, User | None]:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return False, "Liên kết xác minh không hợp lệ.", None

    if not email_verification_token_generator.check_token(user, token):
        return False, "Liên kết xác minh không hợp lệ hoặc đã hết hạn.", user

    identity, _ = AccountEmailIdentity.objects.get_or_create(
        user=user, defaults={"normalized_email": normalize_email(user.email)}
    )
    identity.mark_as_verified()
    return True, "Email của bạn đã được xác minh thành công!", user
