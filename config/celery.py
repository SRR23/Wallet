import os
from pathlib import Path

# Load .env before Django settings so workers see the same variables as manage.py.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from celery import Celery

# Match manage.py. Production workers should set this explicitly:
#   export DJANGO_SETTINGS_MODULE=config.settings.production
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("walletapi")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
