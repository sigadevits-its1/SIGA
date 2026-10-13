from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

GRUPO_ADMINISTRATIVO = "Administrativo"


def es_administrativo(usuario):
    return usuario.is_authenticated and (
        usuario.is_superuser or usuario.groups.filter(name=GRUPO_ADMINISTRATIVO).exists()
    )


def rol_administrativo(vista):
    """Sin sesión: lleva al login. Con sesión pero sin el rol: error 403."""

    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not es_administrativo(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltorio
