from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.admisiones.correos import enviar_aceptacion, enviar_rechazo
from apps.admisiones.cupos import ofertas_con_cupo
from apps.admisiones.models import DocumentoPreinscripcion, Preinscripcion
from apps.admisiones.moodle import MoodleIntegrationError, crear_usuario_moodle
from apps.core.models import Carrera, PeriodoInscripcion

from .permisos import rol_administrativo

Estado = Preinscripcion.Estado
POR_PAGINA = 15


@rol_administrativo
def bandeja(request):
    periodo = PeriodoInscripcion.objects.actual()
    del_periodo = Preinscripcion.objects.filter(periodo_plan__periodo=periodo)

    # Filtros que llegan por la URL: ?q=...&estado=...&carrera=...
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    carrera = request.GET.get("carrera", "")

    solicitudes = (
        del_periodo.select_related("persona", "periodo_plan__plan__carrera")
        .annotate(cantidad_documentos=Count("documentos"))
        .order_by("-fecha_preinscripcion")  # las más recientes primero
    )
    if q:
        busqueda = (
            Q(persona__nombre__icontains=q)
            | Q(persona__apellido__icontains=q)
            | Q(persona__dni__icontains=q)
            | Q(persona__email__icontains=q)
        )
        # Número de solicitud: PRE-2027-00012 -> id 12
        if q.upper().startswith("PRE-") and q.rsplit("-", 1)[-1].isdigit():
            busqueda |= Q(pk=int(q.rsplit("-", 1)[-1]))
        solicitudes = solicitudes.filter(busqueda)
    if estado in Estado.values:
        solicitudes = solicitudes.filter(estado=estado)
    if carrera.isdigit():
        solicitudes = solicitudes.filter(periodo_plan__plan__carrera_id=carrera)

    pagina = Paginator(solicitudes, POR_PAGINA).get_page(request.GET.get("pagina"))

    # Totales por estado para las tarjetas de resumen
    totales = del_periodo.aggregate(
        total=Count("id"),
        pendiente=Count("id", filter=Q(estado=Estado.PENDIENTE)),
        aceptado=Count("id", filter=Q(estado=Estado.ACEPTADO)),
        rechazado=Count("id", filter=Q(estado=Estado.RECHAZADO)),
    )
    tarjetas = [
        {"estado": "", "titulo": "Total", "icono": "users", "tono": "slate", "n": totales["total"]},
        {"estado": Estado.PENDIENTE, "titulo": "Pendientes", "icono": "inbox", "tono": "blue", "n": totales["pendiente"]},
        {"estado": Estado.ACEPTADO, "titulo": "Aceptados", "icono": "circle-check", "tono": "green", "n": totales["aceptado"]},
        {"estado": Estado.RECHAZADO, "titulo": "Rechazados", "icono": "circle-x", "tono": "red", "n": totales["rechazado"]},
    ]

    # Parámetros actuales sin la página, para armar los enlaces del paginador
    filtros = request.GET.copy()
    filtros.pop("pagina", None)

    return render(request, "administracion/bandeja.html", {
        "periodo": periodo,
        "pagina": pagina,
        "tarjetas": tarjetas,
        "totales": totales,
        "ofertas": ofertas_con_cupo(periodo) if periodo else [],
        "carreras": Carrera.objects.filter(activo=True),
        "estados": Estado.choices,
        "f": {"q": q, "estado": estado, "carrera": carrera},
        "filtros_url": filtros.urlencode(),
        "menu": "pendientes" if estado == Estado.PENDIENTE else "todos",
    })


@rol_administrativo
def ficha(request, pk):
    p = get_object_or_404(
        Preinscripcion.objects.select_related(
            "persona", "revisor", "periodo_plan__plan__carrera", "periodo_plan__periodo"
        ),
        pk=pk,
    )
    oferta = next(o for o in ofertas_con_cupo(p.periodo_plan.periodo) if o.pk == p.periodo_plan_id)
    return render(request, "administracion/ficha.html", {
        "p": p,
        "oferta": oferta,
        "documentos": p.documentos.all(),
        "periodo": p.periodo_plan.periodo,
        "menu": "todos",
    })


@require_POST
@rol_administrativo
def aceptar(request, pk):
    p = get_object_or_404(Preinscripcion, pk=pk)
    if not p.esta_pendiente:
        messages.error(request, "La solicitud ya estaba resuelta.")
        return redirect("administracion:ficha", pk=pk)
    cuenta_moodle_existente = bool(p.persona.moodle_user_id)
    try:
        clave_temporal = crear_usuario_moodle(p.persona)
    except MoodleIntegrationError as error:
        messages.error(request, f"No se pudo aceptar la solicitud: {error}")
        return redirect("administracion:ficha", pk=pk)
    p.aceptar(request.user, request.POST.get("observaciones", ""))
    enviar_aceptacion(
        p,
        p.persona.dni,
        clave_temporal,
        cuenta_moodle_existente=cuenta_moodle_existente,
    )
    messages.success(
        request,
        f"Aceptaste a {p.persona.nombre_completo}. Se creó su cuenta de Moodle y le enviamos los datos por correo.",
    )
    return redirect("administracion:ficha", pk=pk)


@require_POST
@rol_administrativo
def rechazar(request, pk):
    p = get_object_or_404(Preinscripcion, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    if not p.esta_pendiente:
        messages.error(request, "La solicitud ya estaba resuelta.")
    elif not motivo:
        messages.error(request, "Para rechazar hay que indicar el motivo.")
    else:
        p.rechazar(request.user, motivo)
        enviar_rechazo(p)
        messages.success(request, f"Rechazaste la solicitud de {p.persona.nombre_completo}. Le avisamos por correo.")
    return redirect("administracion:ficha", pk=pk)


@rol_administrativo
def ver_documento(request, pk):
    """Los archivos no tienen URL pública: se entregan sólo por esta vista."""
    documento = get_object_or_404(DocumentoPreinscripcion, pk=pk)
    return FileResponse(documento.archivo.open("rb"), filename=documento.nombre_original)
