from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView

from .forms import CustomUserCreationForm
from .services import send_verification_email, verify_email_token


class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "auth/register.html"
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            "Tạo tài khoản thành công! Vui lòng kiểm tra hộp thư để xác minh tài khoản, hoặc bấm 'Gửi lại mã xác minh' trên Dashboard nếu chưa nhận được.",
        )
        return response

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class VerifyEmailView(View):
    """Xử lý xác nhận email qua token link."""

    def get(self, request, uidb64, token, *args, **kwargs):
        success, message, user = verify_email_token(uidb64, token)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)

        if request.user.is_authenticated:
            return redirect("dashboard")
        return redirect("accounts:login")


class ResendVerificationEmailView(LoginRequiredMixin, View):
    """Gửi lại email xác minh cho tài khoản đang đăng nhập."""

    def post(self, request, *args, **kwargs):
        success, message = send_verification_email(request.user, request=request)
        if success:
            messages.success(request, message)
        else:
            messages.warning(request, message)
        return redirect("dashboard")

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)
