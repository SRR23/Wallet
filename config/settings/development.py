"""Development settings for WalletAPI."""
import os

from .base import *

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

CORS_ALLOW_ALL_ORIGINS = True

if os.environ.get("EMAIL_BACKEND") is None:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

LOGGING["loggers"]["apps"]["level"] = "DEBUG"
