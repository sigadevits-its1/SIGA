from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("ingresar/", auth_views.LoginView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("administracion/", include("apps.administracion.urls")),
]

# El formulario público es una app "desmontable": si se quita de
# INSTALLED_APPS (por ejemplo, fuera del período de inscripción),
# su dirección deja de existir y el resto del sistema sigue funcionando.
if "apps.preinscripcion" in settings.INSTALLED_APPS:
    urlpatterns += [
        path("preinscripcion/", include("apps.preinscripcion.urls")),
        path("", RedirectView.as_view(pattern_name="preinscripcion:formulario")),
    ]
else:
    urlpatterns += [path("", RedirectView.as_view(pattern_name="administracion:bandeja"))]
