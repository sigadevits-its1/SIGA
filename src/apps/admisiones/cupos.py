"""Cálculo de cupos por carrera dentro de un período."""
from django.db.models import Count, Q

from apps.core.models import PeriodoPlan

from .models import Preinscripcion


def ofertas_con_cupo(periodo):
    """
    Devuelve los planes activos del período con dos datos agregados:
      - ocupados: solicitudes pendientes o aceptadas (las rechazadas liberan el lugar)
      - libres: lugares disponibles, o None si el plan no tiene cupo
    """
    ofertas = (
        PeriodoPlan.objects.filter(periodo=periodo, activo=True)
        .select_related("plan__carrera", "periodo")
        .annotate(
            ocupados=Count(
                "preinscripciones",
                filter=~Q(preinscripciones__estado=Preinscripcion.Estado.RECHAZADO),
            )
        )
        .order_by("plan__carrera__nombre")
    )
    for oferta in ofertas:
        oferta.libres = calcular_libres(oferta.cupo_ingresantes, oferta.ocupados)
    return list(ofertas)


def calcular_libres(cupo, ocupados):
    if cupo is None:
        return None
    return max(cupo - ocupados, 0)


def tiene_cupo(periodo_plan):
    ocupados = periodo_plan.preinscripciones.exclude(estado=Preinscripcion.Estado.RECHAZADO).count()
    libres = calcular_libres(periodo_plan.cupo_ingresantes, ocupados)
    return libres is None or libres > 0
