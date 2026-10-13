from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import migrations


def backfill_email_identities(apps, schema_editor):
    User = apps.get_model("auth", "User")
    AccountEmailIdentity = apps.get_model("accounts", "AccountEmailIdentity")

    users = list(User.objects.all())
    if not users:
        return

    email_map = {}
    invalid_users = []
    duplicate_map = {}

    for user in users:
        raw_email = (user.email or "").strip()
        norm_email = raw_email.lower()

        # Kiểm tra tính hợp lệ của email
        if not norm_email:
            invalid_users.append(f"User(id={user.pk}, username='{user.username}') có email trống")
            continue

        try:
            validate_email(norm_email)
        except ValidationError:
            invalid_users.append(f"User(id={user.pk}, username='{user.username}', email='{raw_email}') email không hợp lệ")
            continue

        if norm_email in email_map:
            if norm_email not in duplicate_map:
                duplicate_map[norm_email] = [email_map[norm_email]]
            duplicate_map[norm_email].append(f"User(id={user.pk}, username='{user.username}')")
        else:
            email_map[norm_email] = f"User(id={user.pk}, username='{user.username}')"

    # Nếu có bất kỳ email trùng lặp hoặc không hợp lệ: Dừng migration theo Spec 17.4
    if invalid_users or duplicate_map:
        error_lines = ["DỪNG MIGRATION: Phát hiện lỗi dữ liệu email người dùng hiện có (Spec 17.4):"]
        if invalid_users:
            error_lines.append("Danh sách tài khoản có email không hợp lệ hoặc rỗng:")
            error_lines.extend(f" - {item}" for item in invalid_users)
        if duplicate_map:
            error_lines.append("Danh sách email bị trùng lặp giữa nhiều tài khoản:")
            for email, conflicts in duplicate_map.items():
                error_lines.append(f" - Email '{email}': {', '.join(conflicts)}")
        error_lines.append("Vui lòng xử lý thủ công các tài khoản trên trước khi tiếp tục migration.")
        raise RuntimeError("\n".join(error_lines))

    # Nếu toàn bộ dữ liệu hợp lệ: backfill AccountEmailIdentity (chưa verified_at)
    identities_to_create = []
    for user in users:
        norm_email = (user.email or "").strip().lower()
        if not AccountEmailIdentity.objects.filter(user=user).exists():
            identities_to_create.append(
                AccountEmailIdentity(
                    user=user,
                    normalized_email=norm_email,
                    verified_at=None,
                )
            )

    if identities_to_create:
        AccountEmailIdentity.objects.bulk_create(identities_to_create)


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(backfill_email_identities, reverse_backfill),
    ]
