from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.admisiones.correos import enviar_recepcion
from apps.admisiones.cupos import ofertas_con_cupo
from apps.admisiones.models import Preinscripcion
from apps.core.models import PeriodoInscripcion

from .forms import PreinscripcionForm


def formulario(request):
    periodo = PeriodoInscripcion.objects.abierto()
    if periodo is None:
        proximo = PeriodoInscripcion.objects.filter(fecha_desde__gt=timezone.now()).order_by("fecha_desde").first()
        return render(request, "preinscripcion/cerrado.html", {"proximo": proximo})

    if request.method == "POST":
        form = PreinscripcionForm(request.POST, request.FILES, periodo=periodo)
        if form.is_valid():
            preinscripcion = form.save()
            enviar_recepcion(preinscripcion)
            # Se guarda en la sesión para que la confirmación no dependa de un id en la URL.
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
