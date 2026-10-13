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
