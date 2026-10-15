"""
Test settings module that guarantees complete database isolation (Spec 12, AC01-AC18).
Uses local SQLite in-memory database (:memory:) for tests.
Prevents any connection to external databases (e.g., Supabase or PostgreSQL).
"""
from .settings import *  # noqa: F403

# Strict isolation: Always use dedicated local test SQLite database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "test_app_db.sqlite3",
        "TEST": {
            "NAME": "test_suite_db.sqlite3",
        },
        "OPTIONS": {
            "timeout": 30,
        },
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Test mode flag for URL routing utilities (Spec B10)
TEST_MODE = True

