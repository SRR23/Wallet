#!/bin/sh
# Wait for Postgres, optionally migrate, then run the container command.
set -e

if [ -n "$DB_HOST" ]; then
  echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT:-5432}..."
  until pg_isready -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" >/dev/null 2>&1; do
    sleep 1
  done
fi

if [ "$RUN_MIGRATIONS" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
