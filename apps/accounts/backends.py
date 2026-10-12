from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    """Cho phép đăng nhập bằng email hoặc username kèm mật khẩu."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_identifier = username or kwargs.get(User.USERNAME_FIELD)
        if login_identifier is None or password is None:
            return None

        try:
            user = User.objects.get(Q(username__iexact=login_identifier) | Q(email__iexact=login_identifier))
        except User.DoesNotExist:
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            user = User.objects.filter(Q(username__iexact=login_identifier) | Q(email__iexact=login_identifier)).order_by("id").first()

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None