from django.urls import path

from . import views

app_name = "administracion"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("aprobados/pdf/", views.exportar_aprobados_pdf, name="aprobados_pdf"),
    path("aspirantes/<int:pk>/", views.ficha, name="ficha"),
    path("aspirantes/<int:pk>/aceptar/", views.aceptar, name="aceptar"),
    path("aspirantes/<int:pk>/rechazar/", views.rechazar, name="rechazar"),
    path("documentos/<int:pk>/", views.ver_documento, name="documento"),
    path("en-construccion/<slug:modulo>/", views.en_construccion, name="en_construccion"),
]
