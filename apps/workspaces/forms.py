import zoneinfo
from django import forms

COMMON_TIMEZONES = [
    ("Asia/Ho_Chi_Minh", "Asia/Ho_Chi_Minh (GMT+7)"),
    ("Asia/Bangkok", "Asia/Bangkok (GMT+7)"),
    ("Asia/Singapore", "Asia/Singapore (GMT+8)"),
    ("Asia/Tokyo", "Asia/Tokyo (GMT+9)"),
    ("UTC", "UTC (GMT+0)"),
    ("Europe/London", "Europe/London (GMT+0)"),
    ("America/New_York", "America/New_York (GMT-5)"),
]


class WorkspaceCreateForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        label="Tên Workspace",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ví dụ: Ban Marketing SaaS",
                "autofocus": True,
            }
        ),
        help_text="Từ 1 đến 100 ký tự. Không được để trống hoặc chỉ có khoảng trắng.",
    )
    timezone = forms.ChoiceField(
        choices=COMMON_TIMEZONES,
        initial="Asia/Ho_Chi_Minh",
        label="Múi giờ hiển thị",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Mặc định là Asia/Ho_Chi_Minh theo chuẩn nghiệp vụ.",
    )

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Tên workspace không được để trống hoặc chỉ chứa khoảng trắng.")
        if len(name) > 100:
            raise forms.ValidationError("Tên workspace không được vượt quá 100 ký tự.")
        return name

    def clean_timezone(self) -> str:
        tz = (self.cleaned_data.get("timezone") or "").strip()
        if not tz or tz not in zoneinfo.available_timezones():
            raise forms.ValidationError("Múi giờ không hợp lệ theo chuẩn IANA.")
        return tz


class WorkspaceUpdateForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        label="Tên Workspace",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ví dụ: Ban Marketing SaaS",
            }
        ),
    )
    timezone = forms.ChoiceField(
        choices=COMMON_TIMEZONES,
        label="Múi giờ hiển thị",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Tên workspace không được để trống hoặc chỉ chứa khoảng trắng.")
        if len(name) > 100:
            raise forms.ValidationError("Tên workspace không được vượt quá 100 ký tự.")
        return name

    def clean_timezone(self) -> str:
        tz = (self.cleaned_data.get("timezone") or "").strip()
        if not tz or tz not in zoneinfo.available_timezones():
            raise forms.ValidationError("Múi giờ không hợp lệ theo chuẩn IANA.")
        return tz


from .models import EmploymentType


class WorkspaceInvitationForm(forms.Form):
    email = forms.EmailField(
        label="Địa chỉ email",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "nguoidung@example.com",
                "autofocus": True,
            }
        ),
        help_text="Email của người bạn muốn mời tham gia workspace. Họ sẽ cần đăng nhập bằng tài khoản có email này.",
    )
    employment_type = forms.ChoiceField(
        choices=EmploymentType.choices,
        initial=EmploymentType.IN_HOUSE,
        label="Hình thức quan hệ",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Nội bộ (IN_HOUSE) hoặc Freelancer / Đối tác ngoài (FREELANCER).",
    )
    ai_use_allowed = forms.BooleanField(
        required=False,
        initial=False,
        label="Cho phép dùng AI",
        help_text="Cấp quyền sử dụng tính năng AI (BYOK) cho thành viên này.",
    )

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            raise forms.ValidationError("Địa chỉ email không hợp lệ.")
        return email


class MemberUpdateForm(forms.Form):
    employment_type = forms.ChoiceField(
        choices=EmploymentType.choices,
        label="Hình thức quan hệ",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    ai_use_allowed = forms.BooleanField(
        required=False,
        label="Cho phép dùng AI",
    )



class BrandProfileForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        label="Tên thương hiệu",
        error_messages={"required": "Tên thương hiệu không được để trống hoặc chỉ có khoảng trắng."},
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ví dụ: Acme Studio",
                "autofocus": True,
            }
        ),
        help_text="Từ 1 đến 100 ký tự. Bắt buộc.",
    )
    product_summary = forms.CharField(
        max_length=5000,
        label="Sản phẩm / Dịch vụ chủ lực",
        error_messages={"required": "Thông tin sản phẩm/dịch vụ không được để trống."},
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Mô tả sản phẩm, dịch vụ của thương hiệu...",
            }
        ),
        help_text="Từ 1 đến 5.000 ký tự. Bắt buộc.",
    )
    target_audience = forms.CharField(
        max_length=3000,
        label="Khách hàng mục tiêu",
        error_messages={"required": "Khách hàng mục tiêu không được để trống."},
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Chân dung đối tượng độc giả, khách hàng mục tiêu...",
            }
        ),
        help_text="Từ 1 đến 3.000 ký tự. Bắt buộc.",
    )
    tone_of_voice = forms.CharField(
        max_length=3000,
        required=False,
        label="Giọng văn thương hiệu",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Ví dụ: Chuyên nghiệp, gần gũi, truyền cảm hứng...",
            }
        ),
        help_text="Tối đa 3.000 ký tự. Tùy chọn.",
    )
    avoid_guidelines = forms.CharField(
        max_length=3000,
        required=False,
        label="Điều cần tránh (Brand Guidelines)",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Các từ ngữ, thông điệp hoặc chủ đề cấm kỵ...",
            }
        ),
        help_text="Tối đa 3.000 ký tự. Tùy chọn.",
    )
    allowed_claims = forms.CharField(
        max_length=3000,
        required=False,
        label="Tuyên bố được phép sử dụng",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Các cam kết, tuyên bố được phép sử dụng trong bài viết...",
            }
        ),
        help_text="Tối đa 3.000 ký tự. Tùy chọn.",
    )
    source_urls = forms.CharField(
        required=False,
        label="Danh sách URL nguồn tham khảo",
        widget=forms.Textarea(
            attrs={
                "class": "form-control font-monospace",
                "rows": 3,
                "placeholder": "https://example.com/brand-guidelines\nhttps://example.com/specs",
            }
        ),
        help_text="Mỗi dòng một URL. Tối đa 10 URL. Bắt buộc sử dụng giao thức HTTPS.",
    )
    expected_revision = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Tên thương hiệu không được để trống hoặc chỉ có khoảng trắng.")
        if len(name) > 100:
            raise forms.ValidationError("Tên thương hiệu không được vượt quá 100 ký tự.")
        return name

    def clean_product_summary(self) -> str:
        val = (self.cleaned_data.get("product_summary") or "").strip()
        if not val:
            raise forms.ValidationError("Thông tin sản phẩm/dịch vụ không được để trống.")
        if len(val) > 5000:
            raise forms.ValidationError("Thông tin sản phẩm không được vượt quá 5.000 ký tự.")
        return val

    def clean_target_audience(self) -> str:
        val = (self.cleaned_data.get("target_audience") or "").strip()
        if not val:
            raise forms.ValidationError("Khách hàng mục tiêu không được để trống.")
        if len(val) > 3000:
            raise forms.ValidationError("Khách hàng mục tiêu không được vượt quá 3.000 ký tự.")
        return val

    def clean_tone_of_voice(self) -> str:
        val = (self.cleaned_data.get("tone_of_voice") or "").strip()
        if len(val) > 3000:
            raise forms.ValidationError("Giọng văn không được vượt quá 3.000 ký tự.")
        return val

    def clean_avoid_guidelines(self) -> str:
        val = (self.cleaned_data.get("avoid_guidelines") or "").strip()
        if len(val) > 3000:
            raise forms.ValidationError("Điều cần tránh không được vượt quá 3.000 ký tự.")
        return val

    def clean_allowed_claims(self) -> str:
        val = (self.cleaned_data.get("allowed_claims") or "").strip()
        if len(val) > 3000:
            raise forms.ValidationError("Tuyên bố được phép không được vượt quá 3.000 ký tự.")
        return val

    def clean_source_urls(self) -> list[str]:
        raw = self.cleaned_data.get("source_urls") or ""
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) > 10:
            raise forms.ValidationError("Tối đa 10 URL nguồn tham khảo.")

        import urllib.parse

        cleaned = []
        for u in lines:
            parsed = urllib.parse.urlparse(u)
            if parsed.scheme.lower() != "https":
                raise forms.ValidationError(f"URL '{u}' không hợp lệ. Chỉ chấp nhận giao thức HTTPS.")
            if not parsed.netloc:
                raise forms.ValidationError(f"URL '{u}' không hợp lệ. Phải có tên miền đầy đủ.")
            cleaned.append(u)
        return cleaned

