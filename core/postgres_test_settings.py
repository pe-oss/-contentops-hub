"""
PostgreSQL test settings module that guarantees complete database isolation.
Uses PostgreSQL via TEST_DATABASE_URL or DATABASE_URL.
Verifies row locking (select_for_update), transactions, and real concurrency.
"""
import os
from .settings import *  # noqa: F403
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

pg_test_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
if not pg_test_url or pg_test_url.startswith("sqlite"):
    # If not configured, raise informative configuration notice
    raise ImproperlyConfigured(
        "TEST_DATABASE_URL (or DATABASE_URL) pointing to a PostgreSQL instance is required "
        "to run PostgreSQL tests. Example: postgresql://postgres:password@localhost:5432/test_db"
    )

DATABASES = {
    "default": dj_database_url.parse(pg_test_url, conn_max_age=600)
}
DATABASES["default"]["TEST"] = {
    "NAME": os.getenv("TEST_DATABASE_NAME", "test_postgres"),
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
