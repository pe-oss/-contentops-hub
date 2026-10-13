from datetime import timedelta
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import AccountEmailIdentity
from apps.accounts.services import (
    create_user_with_identity,
    email_verification_token_generator,
    normalize_email,
    send_verification_email,
    update_user_email,
    verify_email_token,
)

User = get_user_model()


class EmailIdentityModelAndServiceTests(TestCase):
    def test_normalize_email(self):
        self.assertEqual(normalize_email("  User.Test@Example.COM  "), "user.test@example.com")
        self.assertEqual(normalize_email(""), "")
        self.assertEqual(normalize_email(None), "")

    def test_create_user_creates_identity_atomically(self):
        user = create_user_with_identity(
            username="testuser",
            email="TEST@example.com",
            password="StrongPassword123!",
            first_name="Test",
            last_name="User",
            send_email=False,
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(hasattr(user, "email_identity"))
        self.assertEqual(user.email_identity.normalized_email, "test@example.com")
        self.assertFalse(user.email_identity.is_verified)
        self.assertIsNone(user.email_identity.verified_at)

    def test_duplicate_email_rejected_at_db_and_service(self):
        create_user_with_identity(
            username="user1",
            email="duplicate@example.com",
            password="Password123!",
            send_email=False,
        )
        with self.assertRaises(ValidationError):
            create_user_with_identity(
                username="user2",
                email="DUPLICATE@example.com",
                password="Password123!",
                send_email=False,
            )

        # Trực tiếp tại DB constraint
        other_user = User.objects.create_user(username="other", email="other@example.com", password="pwd")
        with self.assertRaises(IntegrityError):
            AccountEmailIdentity.objects.create(
                user=other_user,
                normalized_email="duplicate@example.com",
            )

    def test_update_user_email_resets_verified_at(self):
        user = create_user_with_identity(
            username="user3",
            email="old@example.com",
            password="Password123!",
            send_email=False,
        )
        user.email_identity.mark_as_verified()
        self.assertTrue(user.email_identity.is_verified)

        identity = update_user_email(user, "new@example.com", send_email=False)
        self.assertEqual(identity.normalized_email, "new@example.com")
        self.assertFalse(identity.is_verified)
        self.assertIsNone(identity.verified_at)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")

    def test_update_user_email_rejects_duplicate(self):
        create_user_with_identity(
            username="user_a",
            email="a@example.com",
            password="Password123!",
            send_email=False,
        )
        user_b = create_user_with_identity(
            username="user_b",
            email="b@example.com",
            password="Password123!",
            send_email=False,
        )
        with self.assertRaises(ValidationError):
            update_user_email(user_b, "a@example.com", send_email=False)


class AmbiguousLoginPreventionTests(TestCase):
    def setUp(self):
        # User A có username "user_alpha" và email "alpha@example.com"
        self.user_a = create_user_with_identity(
            username="user_alpha",
            email="alpha@example.com",
            password="AlphaPassword123!",
            send_email=False,
        )
        # User B có username "alpha@example.com" và email "beta@example.com"
        # Tạo tình huống đụng độ: định danh đăng nhập khớp 2 người khác nhau
        self.user_b = create_user_with_identity(
            username="alpha@example.com",
            email="beta@example.com",
            password="BetaPassword123!",
            send_email=False,
        )

    def test_unambiguous_login_by_username_succeeds(self):
        user = authenticate(username="user_alpha", password="AlphaPassword123!")
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user_a.pk)

    def test_unambiguous_login_by_email_succeeds(self):
        user = authenticate(username="beta@example.com", password="BetaPassword123!")
        self.assertIsNotNone(user)
        self.assertEqual(user.pk, self.user_b.pk)

    def test_ambiguous_identifier_matching_two_different_users_is_rejected(self):
        # "alpha@example.com" khớp email của User A và username của User B -> MƠ HỒ
        user = authenticate(username="alpha@example.com", password="AlphaPassword123!")
        self.assertIsNone(user, "Đăng nhập mơ hồ phải bị từ chối tuyệt đối theo Spec 17.4")

        user2 = authenticate(username="alpha@example.com", password="BetaPassword123!")
        self.assertIsNone(user2, "Đăng nhập mơ hồ phải bị từ chối với bất kỳ mật khẩu nào")

    def test_nonexistent_login_returns_none(self):
        user = authenticate(username="nonexistent@example.com", password="pwd")
        self.assertIsNone(user)


class VerificationFlowAndRateLimitTests(TestCase):
    def setUp(self):
        self.user = create_user_with_identity(
            username="verify_user",
            email="verify@example.com",
            password="Password123!",
            send_email=False,
        )

    def test_email_verification_token_cycle(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = email_verification_token_generator.make_token(self.user)

        success, msg, user = verify_email_token(uidb64, token)
        self.assertTrue(success)
        self.assertEqual(user.pk, self.user.pk)
        self.user.email_identity.refresh_from_db()
        self.assertTrue(self.user.email_identity.is_verified)
        self.assertIsNotNone(self.user.email_identity.verified_at)

    def test_invalid_token_rejected(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        success, msg, _ = verify_email_token(uidb64, "invalid-token-123")
        self.assertFalse(success)

    def test_rate_limiting_cooldown(self):
        success1, _ = send_verification_email(self.user)
        self.assertTrue(success1)

        # Gửi lại ngay lập tức -> phải bị rate limit
        success2, msg2 = send_verification_email(self.user)
        self.assertFalse(success2)
        self.assertIn("giây", msg2)

        # Tua thời gian qua 61 giây
        self.user.email_identity.last_verification_sent_at = timezone.now() - timedelta(seconds=65)
        self.user.email_identity.save()

        success3, _ = send_verification_email(self.user)
        self.assertTrue(success3)


class AccountsViewsIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_creates_identity_and_logs_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            data={
                "username": "newregistrant",
                "first_name": "Nguyen",
                "last_name": "An",
                "email": "NEWREG@example.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
                "terms": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="newregistrant")
        self.assertEqual(user.email, "newreg@example.com")
        self.assertTrue(hasattr(user, "email_identity"))
        self.assertFalse(user.email_identity.is_verified)

    def test_verify_email_view_flow(self):
        user = create_user_with_identity(
            username="target_user",
            email="target@example.com",
            password="Password123!",
            send_email=False,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token_generator.make_token(user)

        url = reverse("accounts:verify_email", kwargs={"uidb64": uidb64, "token": token})
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)

        user.email_identity.refresh_from_db()
        self.assertTrue(user.email_identity.is_verified)


class MigrationBackfillHaltTests(TestCase):
    def test_backfill_halts_on_duplicate_emails(self):
        import importlib
        from unittest.mock import MagicMock
        from django.apps import apps

        migration_module = importlib.import_module("apps.accounts.migrations.0002_backfill_email_identities")
        backfill_email_identities = migration_module.backfill_email_identities

        # Giả lập 2 user có cùng normalized email
        user1 = User(id=101, username="alpha", email="DUPLICATE@example.com")
        user2 = User(id=102, username="beta", email="duplicate@example.com")

        mock_user_model = MagicMock()
        mock_user_model.objects.all.return_value = [user1, user2]

        mock_apps = MagicMock()
        def get_model(app_label, model_name):
            if model_name == "User":
                return mock_user_model
            return apps.get_model(app_label, model_name)
        mock_apps.get_model.side_effect = get_model

        with self.assertRaises(RuntimeError) as ctx:
            backfill_email_identities(mock_apps, None)
        self.assertIn("DỪNG MIGRATION", str(ctx.exception))
        self.assertIn("duplicate@example.com", str(ctx.exception))

    def test_backfill_halts_on_invalid_or_empty_email(self):
        import importlib
        from unittest.mock import MagicMock
        from django.apps import apps

        migration_module = importlib.import_module("apps.accounts.migrations.0002_backfill_email_identities")
        backfill_email_identities = migration_module.backfill_email_identities

        user_invalid = User(id=201, username="bad_email", email="not-an-email")

        mock_user_model = MagicMock()
        mock_user_model.objects.all.return_value = [user_invalid]

        mock_apps = MagicMock()
        def get_model(app_label, model_name):
            if model_name == "User":
                return mock_user_model
            return apps.get_model(app_label, model_name)
        mock_apps.get_model.side_effect = get_model

        with self.assertRaises(RuntimeError) as ctx:
            backfill_email_identities(mock_apps, None)
        self.assertIn("DỪNG MIGRATION", str(ctx.exception))
        self.assertIn("bad_email", str(ctx.exception))



