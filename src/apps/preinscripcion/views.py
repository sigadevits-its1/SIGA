from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.admisiones.correos import enviar_recepcion
from apps.admisiones.cupos import ofertas_con_cupo
from apps.admisiones.models import DocumentoPreinscripcion, Preinscripcion
from apps.admisiones.servicios import CupoAgotado, SolicitudDuplicada, registrar_preinscripcion
from apps.core.models import PeriodoInscripcion

from .forms import PreinscripcionForm


def formulario(request):
    periodo = PeriodoInscripcion.objects.abierto()  # o obtener_abierto() si renombrás
    if periodo is None:
        proximo = PeriodoInscripcion.objects.filter(
            fecha_desde__gt=timezone.now()
        ).order_by("fecha_desde").first()
        return render(request, "preinscripcion/cerrado.html", {"proximo": proximo})

    if request.method == "POST":
        form = PreinscripcionForm(request.POST, request.FILES, periodo=periodo)
        # Toda la escritura vive en el servicio: si no hay cupo o hay
        # duplicado, no queda ninguna fila ni documento a medias.
        if form.is_valid():
            archivos = {
                DocumentoPreinscripcion.Tipo.DNI: form.cleaned_data["archivo_dni"],
                form.cleaned_data["titulo_situacion"]: form.cleaned_data["archivo_titulo"],
                DocumentoPreinscripcion.Tipo.ANALITICO: form.cleaned_data.get("archivo_analitico"),
            }
            try:
                preinscripcion = registrar_preinscripcion(
                    datos=form.cleaned_data,
                    archivos=archivos,
                )
            except CupoAgotado:
                form.add_error("oferta", "Esta carrera no tiene cupo disponible.")
            except SolicitudDuplicada:
                form.add_error("dni", "Ya existe una solicitud activa con este DNI.")
            else:
                enviar_recepcion(preinscripcion)
                request.session["preinscripcion_enviada"] = preinscripcion.pk
                return redirect("preinscripcion:enviada")
    else:
        form = PreinscripcionForm(periodo=periodo)

    return render(request, "preinscripcion/formulario.html", {
        "form": form,
        "periodo": periodo,
        "ofertas": ofertas_con_cupo(periodo),
    })


def enviada(request):
    pk = request.session.get("preinscripcion_enviada")
    if pk is None:
        return redirect("preinscripcion:formulario")
    preinscripcion = get_object_or_404(
        Preinscripcion.objects.select_related("persona", "periodo_plan__plan__carrera", "periodo_plan__periodo"),
        pk=pk,
    )
    return render(request, "preinscripcion/enviada.html", {"p": preinscripcion})
