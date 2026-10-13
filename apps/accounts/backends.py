import logging
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import AccountEmailIdentity
from .services import normalize_email

logger = logging.getLogger(__name__)
User = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Xác thực qua email (thông qua AccountEmailIdentity) hoặc username.
    Từ chối tuyệt đối trường hợp mơ hồ (nhiều tài khoản hoặc khớp hai người khác nhau).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_identifier = username or kwargs.get(User.USERNAME_FIELD)
        if not login_identifier or password is None:
            return None

        login_str = str(login_identifier).strip()
        norm_email = normalize_email(login_str)

        # 1. Tìm user qua AccountEmailIdentity
        identity_user = None
        if norm_email:
            matching_identities = list(
                AccountEmailIdentity.objects.filter(normalized_email=norm_email).select_related("user")[:2]
            )
            if len(matching_identities) > 1:
                # Dữ liệu bất thường, từ chối để tránh đoán tài khoản
                User().set_password(password)
                return None
            if matching_identities:
                identity_user = matching_identities[0].user

        # 2. Tìm user qua username
        username_user = None
        matching_usernames = list(User.objects.filter(username__iexact=login_str)[:2])
        if len(matching_usernames) > 1:
            User().set_password(password)
            return None
        if matching_usernames:
            username_user = matching_usernames[0]

        # 3. Kiểm tra tính rõ ràng (ambiguity)
        target_user = None
        if identity_user and username_user:
            if identity_user.pk != username_user.pk:
                # Đụng độ: chuỗi nhập vừa là username của User A vừa là email của User B
                logger.warning(
                    "Đăng nhập bị từ chối do mơ hồ giữa User PK=%s và User PK=%s",
                    identity_user.pk,
                    username_user.pk,
                )
                User().set_password(password)
                return None
            target_user = identity_user
        elif identity_user:
            target_user = identity_user
        elif username_user:
            target_user = username_user
        else:
            User().set_password(password)
            return None

        # 4. Kiểm tra mật khẩu và quyền đăng nhập
        if target_user.check_password(password) and self.user_can_authenticate(target_user):
            return target_user

        return None
