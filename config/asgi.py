"""
ASGI config for WalletAPI.

Exposes the ASGI callable as ``application``.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_asgi_application()
