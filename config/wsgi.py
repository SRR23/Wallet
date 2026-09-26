"""
WSGI config for WalletAPI.

Exposes the WSGI callable as ``application``.
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

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_wsgi_application()
