from django.urls import path

from . import views

app_name = "preinscripcion"

urlpatterns = [
    path("", views.formulario, name="formulario"),
    path("enviada/", views.enviada, name="enviada"),
]
