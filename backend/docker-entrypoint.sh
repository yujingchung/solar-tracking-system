#!/bin/bash
set -e

if [ "$DATABASE" = "mysql" ]; then
    echo "Waiting for MySQL..."
    while ! nc -z "$SQL_HOST" "$SQL_PORT"; do
      sleep 0.1
    done
    echo "MySQL is ready"
fi

echo "Applying database migrations..."
python manage.py makemigrations
python manage.py migrate

exec "$@"
