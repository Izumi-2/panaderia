from django.conf import settings
from django.shortcuts import redirect


class ForceLoginMiddleware:
    """Redirige a la página de login si el usuario no está autenticado.

    Excepciones típicas: rutas de login, archivos estáticos, media y favicon.
    Ajusta `FORCE_LOGIN_EXEMPT_PATHS` en `settings.py` si necesitas más excepciones.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ''

        # Rutas exentas por defecto
        exempt_paths = getattr(settings, 'FORCE_LOGIN_EXEMPT_PATHS', None)
        if exempt_paths is None:
            exempt_paths = [
                '/accounts/login/',
                '/accounts/logged-out/',
                '/accounts/password-reset-by-word/',
                '/favicon.ico',
                '/static/',
                '/media/',
                '/admin/login/',
                '/admin/logout/',
            ]

        for p in exempt_paths:
            if path.startswith(p):
                return self.get_response(request)

        # Si el usuario está autenticado, permitir la petición
        if request.user.is_authenticated:
            return self.get_response(request)

        # Si es petición AJAX o espera JSON, devolver 401 en vez de redirigir
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        if is_ajax:
            from django.http import JsonResponse
            return JsonResponse({'detail': 'Authentication credentials were not provided.'}, status=401)

        # En cualquier otro caso, redirigir al login configurado
        login_url = getattr(settings, 'FORCE_LOGIN_REDIRECT_URL', None) or '/accounts/login/'
        return redirect(login_url)
