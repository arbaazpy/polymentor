#!/usr/bin/env bash
# Render build step. Idempotent: safe on every deploy.
set -o errexit

pip install --quiet uv
uv sync --frozen --no-dev
uv run python manage.py collectstatic --noinput
uv run python manage.py migrate --noinput
uv run python manage.py sync_experts

# Optional admin user for reviewing learned exemplars (set both env vars).
if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  uv run python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" || true
fi
