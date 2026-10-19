import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class ProductionSettingsFailFastTests(SimpleTestCase):
    def test_production_fails_when_debug_is_true(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "True", "SECRET_KEY": "a-strong-prod-key-1234567890", "DATABASE_URL": "postgres://localhost/db", "ALLOWED_HOSTS": "example.com"}):
            import importlib
            import core.settings
            with self.assertRaises(ImproperlyConfigured) as ctx:
                importlib.reload(core.settings)
            self.assertIn("DEBUG must be set to False in production", str(ctx.exception))

    def test_production_fails_without_secret_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "False", "SECRET_KEY": "", "DATABASE_URL": "postgres://localhost/db", "ALLOWED_HOSTS": "example.com"}):
            import importlib
            import core.settings
            with self.assertRaises(ImproperlyConfigured) as ctx:
                importlib.reload(core.settings)
            self.assertIn("SECRET_KEY must be configured", str(ctx.exception))

    def test_production_fails_with_insecure_secret_key(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "False", "SECRET_KEY": "django-insecure-test", "DATABASE_URL": "postgres://localhost/db", "ALLOWED_HOSTS": "example.com"}):
            import importlib
            import core.settings
            with self.assertRaises(ImproperlyConfigured) as ctx:
                importlib.reload(core.settings)
            self.assertIn("SECRET_KEY must be configured", str(ctx.exception))

    def test_production_fails_without_database_url(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "False", "SECRET_KEY": "a-very-strong-production-secret-key-12345", "DATABASE_URL": "", "ALLOWED_HOSTS": "example.com"}):
            import importlib
            import core.settings
            with self.assertRaises(ImproperlyConfigured) as ctx:
                importlib.reload(core.settings)
            self.assertIn("DATABASE_URL must be configured in production", str(ctx.exception))

    def test_production_fails_with_sqlite_database_url(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "False", "SECRET_KEY": "a-very-strong-production-secret-key-12345", "DATABASE_URL": "sqlite:///local.db", "ALLOWED_HOSTS": "example.com"}):
            import importlib
            import core.settings
            with self.assertRaises(ImproperlyConfigured) as ctx:
                importlib.reload(core.settings)
            self.assertIn("SQLite is not permitted in production", str(ctx.exception))

    def tearDown(self):
        import importlib
        import core.settings
        importlib.reload(core.settings)


class BillingDisabledRoutesTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="billinguser",
            email="billinguser@example.com",
            password="StrongPassword123!",
        )

    @override_settings(BILLING_ENABLED=False)
    def test_pricing_view_returns_404_when_billing_disabled(self):
        response = self.client.get(reverse("pricing"))
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_checkout_create_returns_404_when_billing_disabled(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("payments:checkout_create", kwargs={"plan_type": "pro"}))
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_checkout_detail_returns_404_when_billing_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payments:checkout_detail", kwargs={"order_id": 999}))
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_checkout_status_returns_404_when_billing_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("payments:checkout_status", kwargs={"order_id": 999}))
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_payos_webhook_returns_404_when_billing_disabled(self):
        response = self.client.post(reverse("payments:payos_webhook"), data={}, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_sepay_webhook_returns_404_when_billing_disabled(self):
        response = self.client.post(reverse("payments:sepay_webhook"), data={}, content_type="application/json")
        self.assertEqual(response.status_code, 404)

    @override_settings(BILLING_ENABLED=False)
    def test_home_page_hides_pricing_link_when_billing_disabled(self):
        response = self.client.get(reverse("home"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/pricing/"')
        self.assertNotContains(response, "Xem bảng giá")

    @override_settings(BILLING_ENABLED=False)
    def test_dashboard_hides_billing_elements_when_billing_disabled(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Lịch sử thanh toán")
        self.assertNotContains(response, "Gói dịch vụ")


class AuthWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_login_username_email_and_change_password(self):
        # 1. Register
        register_data = {
            "first_name": "Nguyen",
            "last_name": "Tester",
            "username": "tester1",
            "email": "tester1@example.com",
            "password1": "PasswordA123!",
            "password2": "PasswordA123!",
            "terms": "on",
        }
        resp = self.client.post(reverse("accounts:register"), data=register_data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="tester1").exists())

        # 2. Logout
        self.client.post(reverse("accounts:logout"))

        # 3. Login with username
        resp = self.client.post(reverse("accounts:login"), data={"username": "tester1", "password": "PasswordA123!"})
        self.assertEqual(resp.status_code, 302)
        self.client.post(reverse("accounts:logout"))

        # 4. Login with email
        resp = self.client.post(reverse("accounts:login"), data={"username": "tester1@example.com", "password": "PasswordA123!"})
        self.assertEqual(resp.status_code, 302)

        # 5. Change password
        change_data = {
            "old_password": "PasswordA123!",
            "new_password1": "PasswordB456!",
            "new_password2": "PasswordB456!",
        }
        resp = self.client.post(reverse("accounts:password_change"), data=change_data)


class StaticfilesServingTests(TestCase):
    def test_static_css_served_successfully(self):
        client = Client()
        resp = client.get("/static/css/app.css")
        self.assertEqual(resp.status_code, 200)
        body = b"".join(resp.streaming_content)
        self.assertGreater(len(body), 100)

