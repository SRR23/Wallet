# WalletAPI application image (local Compose).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/production.txt /app/requirements/
RUN pip install -r /app/requirements/production.txt

COPY . /app

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media

EXPOSE 8000

ENV PORT=8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
