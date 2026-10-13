from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .forms import EmailOrUsernameAuthenticationForm
from .views import RegisterView, ResendVerificationEmailView, VerifyEmailView

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="auth/login.html",
            authentication_form=EmailOrUsernameAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/<str:uidb64>/<str:token>/", VerifyEmailView.as_view(), name="verify_email"),
    path("resend-verification/", ResendVerificationEmailView.as_view(), name="resend_verification"),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="auth/password_change.html",
            success_url=reverse_lazy("accounts:password_change_done"),
        ),
        name="password_change",
    ),
    path("password-change/done/", auth_views.PasswordChangeDoneView.as_view(template_name="auth/password_change_done.html"), name="password_change_done"),
]
