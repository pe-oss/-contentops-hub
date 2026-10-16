#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/2] Running database migrations ==="
python manage.py migrate --noinput

echo "=== [2/2] Starting Gunicorn application server ==="
exec python -m gunicorn core.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2
