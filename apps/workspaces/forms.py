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

from .models import Membership, MembershipStatus, TaskExecutionMode


class PackageForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        label="Tên gói nội dung",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ví dụ: Chiến dịch Tuyển sinh Quý 4", "autofocus": True}
        ),
        help_text="1–150 ký tự.",
    )
    objective = forms.CharField(
        max_length=3000,
        label="Mục tiêu của gói",
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3, "placeholder": "Mục tiêu truyền thông, định vị và kết quả kỳ vọng..."}
        ),
        help_text="1–3.000 ký tự.",
    )
    coordinator_membership = forms.ModelChoiceField(
        queryset=Membership.objects.none(),
        label="Thành viên điều phối",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Người chịu trách nhiệm điều phối tiến độ của gói.",
    )
    start_date = forms.DateField(
        label="Ngày bắt đầu",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    end_date = forms.DateField(
        label="Ngày kết thúc",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    channel = forms.CharField(
        initial="FACEBOOK",
        required=False,
        label="Kênh xuất bản",
        widget=forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
        help_text="Kênh cố định FACEBOOK trong phiên bản R1.",
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, workspace=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.workspace = workspace
            self.fields["coordinator_membership"].queryset = (
                Membership.objects.filter(workspace=workspace, status=MembershipStatus.ACTIVE)
                .select_related("user")
                .order_by("user__first_name", "user__email")
            )
            self.fields["coordinator_membership"].label_from_instance = (
                lambda m: f"{m.user.get_full_name() or m.user.username} ({m.user.email})"
            )

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Tên gói nội dung không được để trống.")
        if len(name) > 150:
            raise forms.ValidationError("Tên gói nội dung không được vượt quá 150 ký tự.")
        return name

    def clean_objective(self) -> str:
        obj = (self.cleaned_data.get("objective") or "").strip()
        if not obj:
            raise forms.ValidationError("Mục tiêu của gói không được để trống.")
        if len(obj) > 3000:
            raise forms.ValidationError("Mục tiêu không được vượt quá 3.000 ký tự.")
        return obj

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "Ngày kết thúc không được trước ngày bắt đầu.")
        return cleaned_data


class ContentDraftForm(forms.Form):
    """Form lưu nháp bài viết cho người viết (F03)."""
    text = forms.CharField(
        required=False,
        label="Nội dung bản nháp",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 10,
                "placeholder": "Soạn thảo bài viết hoặc dán nội dung từ AI tại đây...",
            }
        ),
    )
    reference_urls_text = forms.CharField(
        required=False,
        label="URLs tham khảo / kiểm chứng (mỗi URL một dòng, giao thức HTTPS)",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "https://example.com/source1\nhttps://example.com/source2",
            }
        ),
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


class ContentSubmitForm(forms.Form):
    """Form nộp bài viết cho biên tập (F03, AC06)."""
    text = forms.CharField(
        required=True,
        label="Nội dung bài viết",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 12,
                "placeholder": "Nhập toàn văn nội dung bài viết hoàn chỉnh...",
            }
        ),
    )
    reference_urls_text = forms.CharField(
        required=False,
        label="URLs tham khảo / nguồn tư liệu (HTTPS)",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "https://example.com/source1",
            }
        ),
    )
    source = forms.ChoiceField(
        choices=TaskExecutionMode.choices,
        initial=TaskExecutionMode.MANUAL,
        label="Hình thức viết bài",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    idempotency_key = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )


class EditorVersionForm(forms.Form):
    """Form biên tập viên tạo phiên bản chỉnh sửa mới (F04, AC06)."""
    text = forms.CharField(
        required=True,
        label="Nội dung sau khi chỉnh sửa",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 12,
                "placeholder": "Chỉnh sửa nội dung cho phiên bản mới...",
            }
        ),
    )
    reference_urls_text = forms.CharField(
        required=False,
        label="URLs tham khảo / nguồn bổ sung (HTTPS)",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "https://example.com/source1",
            }
        ),
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


class RequestChangesForm(forms.Form):
    """Form biên tập viên yêu cầu người viết sửa lại (F04, AC06)."""
    reason = forms.CharField(
        required=True,
        label="Lý do và yêu cầu cần sửa",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Chỉ rõ các điểm chưa đạt brief, sai lệch dữ liệu, hoặc giọng văn cần điều chỉnh...",
            }
        ),
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


class SubmitReviewForm(forms.Form):
    """Form biên tập viên đánh dấu hoàn tất checklist và nộp Chủ duyệt (F04, 6.1)."""
    brief_compliance = forms.BooleanField(
        required=True,
        label="1. Đúng brief, mục tiêu chiến dịch và yêu cầu bài viết",
    )
    factual_accuracy = forms.BooleanField(
        required=True,
        label="2. Đảm bảo độ chính xác của số liệu và tài liệu cung cấp",
    )
    voice_tone = forms.BooleanField(
        required=True,
        label="3. Đúng định vị, giọng văn thương hiệu và không vi phạm điều tránh",
    )
    cta_verified = forms.BooleanField(
        required=True,
        label="4. Kêu gọi hành động (CTA) đã kiểm tra và phù hợp",
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )
    idempotency_key = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
class ContentItemForm(forms.Form):
    title = forms.CharField(
        max_length=200,
        label="Tiêu đề bài viết",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Ví dụ: 5 bí quyết luyện nghe IELTS Band 7.0+", "autofocus": True}
        ),
        help_text="1–200 ký tự.",
    )
    brief = forms.CharField(
        max_length=5000,
        label="Brief / Yêu cầu nội dung",
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "placeholder": "Yêu cầu chi tiết, góc tiếp cận, thông điệp chính..."}
        ),
        help_text="1–5.000 ký tự.",
    )
    cta = forms.CharField(
        max_length=500,
        required=False,
        label="Kêu gọi hành động (CTA)",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ví dụ: Đăng ký nhận tài liệu miễn phí tại link bên dưới"}),
        help_text="Tối đa 500 ký tự. Tùy chọn.",
    )
    writing_deadline = forms.DateTimeField(
        label="Hạn hoàn thành viết bài",
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )
    editing_deadline = forms.DateTimeField(
        label="Hạn hoàn thành biên tập",
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )
    review_deadline = forms.DateTimeField(
        label="Hạn Chủ duyệt",
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )
    planned_publish_at = forms.DateTimeField(
        label="Thời điểm dự kiến đăng",
        widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
    )
    writer_membership = forms.ModelChoiceField(
        queryset=Membership.objects.none(),
        label="Người viết bài",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    editor_membership = forms.ModelChoiceField(
        queryset=Membership.objects.none(),
        label="Người biên tập",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    publisher_membership = forms.ModelChoiceField(
        queryset=Membership.objects.none(),
        label="Người xuất bản",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    expected_row_version = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, workspace=None, package=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.package = package
        if workspace:
            self.workspace = workspace
            active_members = (
                Membership.objects.filter(workspace=workspace, status=MembershipStatus.ACTIVE)
                .select_related("user")
                .order_by("user__first_name", "user__email")
            )
            for f in ["writer_membership", "editor_membership", "publisher_membership"]:
                self.fields[f].queryset = active_members
                self.fields[f].label_from_instance = (
                    lambda m: f"{m.user.get_full_name() or m.user.username} ({m.user.email})"
                )

    def clean_title(self) -> str:
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Tiêu đề bài viết không được để trống.")
        if len(title) > 200:
            raise forms.ValidationError("Tiêu đề bài viết không được vượt quá 200 ký tự.")
        return title

    def clean_brief(self) -> str:
        b = (self.cleaned_data.get("brief") or "").strip()
        if not b:
            raise forms.ValidationError("Brief bài viết không được để trống.")
        if len(b) > 5000:
            raise forms.ValidationError("Brief bài viết không được vượt quá 5.000 ký tự.")
        return b

    def clean(self):
        cleaned_data = super().clean()
        w_dl = cleaned_data.get("writing_deadline")
        e_dl = cleaned_data.get("editing_deadline")
        r_dl = cleaned_data.get("review_deadline")
        p_at = cleaned_data.get("planned_publish_at")

        if w_dl and e_dl and w_dl > e_dl:
            self.add_error("editing_deadline", "Hạn biên tập không được trước hạn viết bài.")
        if e_dl and r_dl and e_dl > r_dl:
            self.add_error("review_deadline", "Hạn Chủ duyệt không được trước hạn biên tập.")
        if r_dl and p_at and r_dl > p_at:
            self.add_error("planned_publish_at", "Thời điểm dự kiến đăng không được trước hạn Chủ duyệt.")

        if self.package:
            if self.package.start_date and w_dl and w_dl.date() < self.package.start_date:
                self.add_error(
                    "writing_deadline",
                    f"Hạn viết ({w_dl.date()}) không được trước ngày bắt đầu của gói ({self.package.start_date}).",
                )
            if self.package.end_date and p_at and p_at.date() > self.package.end_date:
                self.add_error(
                    "planned_publish_at",
                    f"Thời điểm dự kiến đăng ({p_at.date()}) không được sau ngày kết thúc của gói ({self.package.end_date}).",
                )
        return cleaned_data


