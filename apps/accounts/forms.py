from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class CustomUserCreationForm(UserCreationForm):
    first_name = forms.CharField(
        label="Họ",
        max_length=150,
        required=True,
        error_messages={"required": "Vui lòng nhập họ của bạn."},
        widget=forms.TextInput(attrs={"placeholder": "Nguyễn", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        label="Tên",
        max_length=150,
        required=True,
        error_messages={"required": "Vui lòng nhập tên của bạn."},
        widget=forms.TextInput(attrs={"placeholder": "Văn A", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        label="Email",
        required=True,
        error_messages={
            "required": "Vui lòng nhập địa chỉ email.",
            "invalid": "Địa chỉ email không hợp lệ.",
        },
        widget=forms.EmailInput(attrs={"placeholder": "ban@example.com", "autocomplete": "email"}),
    )
    terms = forms.BooleanField(
        label="Tôi đồng ý với Điều khoản dịch vụ và Chính sách bảo mật",
        required=True,
        error_messages={"required": "Bạn cần đồng ý với Điều khoản dịch vụ và Chính sách bảo mật để tiếp tục."},
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "username", "email", "password1", "password2", "terms")
        labels = {
            "username": "Tên đăng nhập",
            "password1": "Mật khẩu",
            "password2": "Xác nhận mật khẩu",
        }
        widgets = {
            "username": forms.TextInput(attrs={"placeholder": "ten_dang_nhap", "autocomplete": "username"}),
        }
        error_messages = {
            "username": {
                "required": "Vui lòng nhập tên đăng nhập.",
                "unique": "Tên đăng nhập này đã được sử dụng.",
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Mật khẩu"
        self.fields["password1"].widget.attrs.update({"placeholder": "Nhập mật khẩu", "autocomplete": "new-password"})
        self.fields["password2"].label = "Xác nhận mật khẩu"
        self.fields["password2"].widget.attrs.update({"placeholder": "Nhập lại mật khẩu", "autocomplete": "new-password"})
        self.fields["username"].help_text = ""
        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""
        self.fields["password2"].error_messages.update({"password_mismatch": "Hai mật khẩu không khớp."})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email này đã được sử dụng bởi tài khoản khác.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email hoặc tên đăng nhập",
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "email@example.com hoặc username"}),
        error_messages={"required": "Vui lòng nhập email hoặc tên đăng nhập."},
    )
    password = forms.CharField(
        label="Mật khẩu",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Nhập mật khẩu"}),
        error_messages={"required": "Vui lòng nhập mật khẩu."},
    )

    error_messages = {
        "invalid_login": "Thông tin đăng nhập không đúng. Vui lòng kiểm tra email/tên đăng nhập và mật khẩu.",
        "inactive": "Tài khoản này đã bị vô hiệu hóa.",
    }