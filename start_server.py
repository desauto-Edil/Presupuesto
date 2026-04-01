#!/usr/bin/env python3
import sys
import os
os.chdir("/Users/u18810/Documents/Automatizacion/Presupuestos/imperandina")
sys.path.insert(0, "/Users/u18810/Documents/Automatizacion/Presupuestos/imperandina")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "imperandina.settings")

# Add venv site-packages
import site
site.addsitedir("/Users/u18810/Documents/Automatizacion/Presupuestos/venv/lib/python3.9/site-packages")

from django.core.management import execute_from_command_line
execute_from_command_line(["manage.py", "runserver", "0.0.0.0:8000"])
