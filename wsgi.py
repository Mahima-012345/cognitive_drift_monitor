# cognitive_drift_monitor/wsgi.py
"""
WSGI config for cognitive_drift_monitor project.
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cognitive_drift_monitor.settings')
application = get_wsgi_application()
