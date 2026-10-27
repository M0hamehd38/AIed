#!/bin/sh
set -e
python manage.py migrate --noinput
# demo data only when a demo password is given
if [ -n "$DEMO_TEACHER_PASSWORD" ]; then python manage.py seed_demo; fi
# ASGI server: pages and the live sessions' WebSockets on one port
exec daphne --bind 0.0.0.0 --port 8000 --proxy-headers config.asgi:application
