#!/bin/sh
set -e
python manage.py migrate --noinput
# demo data only when a demo password is given
if [ -n "$DEMO_TEACHER_PASSWORD" ]; then python manage.py seed_demo; fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile -
