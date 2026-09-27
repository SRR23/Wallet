"""
Shared settings for WalletAPI.

Environment-specific overrides live in development.py and production.py.
This file wires the project. It does not implement wallet or tenant rules.
"""
import os
from datetime import timedelta
from pathlib import Path

try:
    import dj_database_url
except ImportError:
    dj_database_url = None

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-this-in-production")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.tenants",
    "apps.wallets",
    "apps.ledger",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Tenant scoping belongs in apps.tenants.middleware. Register it there
    # after the class actually resolves the tenant. Do not register a no-op.
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# DATABASE_URL is for hosted Postgres. Local runs use DB_* variables.
if dj_database_url and os.environ.get("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.config(
            default=os.environ.get("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "walletapi"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# Django AUTH_USER_MODEL is for platform super admin only.
# Tenant accounts are apps.tenants.models.User (JWT + X-Tenant-ID).

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Platform operators use JWT. Tenant wallet APIs also use X-Tenant-ID.
# Super-admin reads require is_superuser (see utils.permissions.IsSuperUser).
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "EXCEPTION_HANDLER": "utils.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8001",
]
CORS_ALLOW_CREDENTIALS = True

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "walletapi",
        "TIMEOUT": 300,
    }
}

# EMAIL_BACKEND = os.environ.get(
#     "EMAIL_BACKEND",
#     "django.core.mail.backends.smtp.EmailBackend",
# )
# DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@localhost")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Wallet API — Multi-Tenant Ledger",
    "DESCRIPTION": (
        "## Overview\n"
        "REST API for a multi-tenant wallet and immutable ledger.\n\n"
        "### Actors\n"
        "- **Tenant user** — registers/logs in under a tenant (`X-Tenant-ID` + JWT). "
        "Owns one wallet. Uses `/api/wallets/*` and `/api/ledger/*`.\n"
        "- **Platform super admin** — Django `createsuperuser`. "
        "Uses `/api/auth/admin/login/` then list tenants/users.\n\n"
        "### Typical flow\n"
        "1. `POST /api/tenants/` → save tenant `id`\n"
        "2. `POST /api/auth/register/` with header `X-Tenant-ID` → user + wallet + tokens\n"
        "3. Call deposit / withdraw / transfer with Bearer token + same `X-Tenant-ID`\n"
        "4. `GET /api/wallets/me/` and `.../transactions/` for balance and history\n\n"
        "### Money\n"
        "Amounts are **integers in minor units** (BDT paisa). "
        "`1000` = 10.00 BDT. Never send floats.\n\n"
        "### Idempotency\n"
        "Mutating ledger endpoints require `idempotency_key` (unique per tenant). "
        "A retry returns the original transaction with `replayed: true` (HTTP 200).\n\n"
        "### Auth headers\n"
        "- Tenant APIs: `Authorization: Bearer <tenant access>` **and** `X-Tenant-ID: <tenant uuid>`\n"
        "- Admin APIs: `Authorization: Bearer <superadmin access>`\n\n"
        "In DEBUG, Swagger may auto-fill a superadmin token; tenant-user calls still need "
        "a tenant JWT and `X-Tenant-ID`."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/",
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "jwtAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "JWT access token. Tenant-user token from register/login, "
                    "or platform superadmin token from /api/auth/admin/login/."
                ),
            }
        }
    },
    "SECURITY": [{"jwtAuth": []}],
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "list",
        "tagsSorter": "alpha",
        "operationsSorter": "alpha",
    },
    "TAGS": [
        {"name": "tenants", "description": "Create and (superadmin) inspect tenants."},
        {"name": "users", "description": "Superadmin listing of domain users under tenants."},
        {"name": "auth", "description": "Tenant-user register/login/refresh/me and admin login."},
        {"name": "wallets", "description": "Wallet balance and paginated ledger history."},
        {"name": "ledger", "description": "Deposit, withdraw, and transfer (idempotent)."},
    ],
}
