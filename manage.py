#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Load environment variables from .env before Django settings are imported.
try:
    from pathlib import Path

    from dotenv import load_dotenv

    base_dir = Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
