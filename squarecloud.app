# Quality Life Django / Square Cloud
MAIN=manage.py
MEMORY=512
VERSION=recommended
DISPLAY_NAME=Quality Life
SUBDOMAIN=quality-life-mvrg23
AUTORESTART=true
START=python manage.py collectstatic --noinput && python manage.py release && python -m gunicorn config.wsgi:application --bind 0.0.0.0:80 --workers 2 --timeout 60
