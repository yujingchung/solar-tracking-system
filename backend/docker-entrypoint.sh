#!/bin/bash

if [ "$DATABASE" = "mysql" ]
then
    echo "等待MySQL啟動..."
    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done
    echo "MySQL已啟動"
fi

echo "執行資料庫遷移..."
python manage.py makemigrations
python manage.py migrate

exec "$@"