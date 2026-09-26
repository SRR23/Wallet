.PHONY: help install migrate runserver celery celery-beat test clean

help:
	@echo "WalletAPI - Django Backend Makefile"
	@echo ""
	@echo "Available commands:"
	@echo "  make install          - Install dependencies"
	@echo "  make migrate          - Run database migrations"
	@echo "  make createsuperuser  - Create Django superuser"
	@echo "  make runserver        - Run development server"
	@echo "  make celery           - Run Celery worker"
	@echo "  make celery-beat      - Run Celery beat scheduler"
	@echo "  make test             - Run tests"
	@echo "  make clean            - Clean Python cache files"

install:
	pip install -r requirements.txt

migrate:
	python manage.py makemigrations
	python manage.py migrate

createsuperuser:
	python manage.py createsuperuser

runserver:
	python manage.py runserver

celery:
	celery -A config worker -l info

celery-beat:
	celery -A config beat -l info

test:
	pytest

clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
