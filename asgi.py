# cognitive_drift_monitor/asgi.py
"""
ASGI config for cognitive_drift_monitor project.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cognitive_drift_monitor.settings')
application = get_asgi_application()
