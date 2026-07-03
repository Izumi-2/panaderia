import os
import django
from django.urls import resolve

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'panaderia_project.settings')

django.setup()

try:
    match = resolve('/productos/nuevo/')
    print('view_name:', getattr(match, 'view_name', None))
    print('func:', match.func)
    print('args:', match.args)
    print('kwargs:', match.kwargs)
except Exception as e:
    print('Resolve error:', type(e).__name__, str(e))
