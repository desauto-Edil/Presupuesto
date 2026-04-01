#!/bin/bash
export DJANGO_SETTINGS_MODULE=imperandina.settings
cd /Users/u18810/Documents/Automatizacion/Presupuestos/imperandina
exec /Users/u18810/Documents/Automatizacion/Presupuestos/venv/bin/python3.9 manage.py runserver 0.0.0.0:8000
