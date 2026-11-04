"""Servicios de preinscripciones: alta, aceptación y rechazo.

Concentran las reglas que no deben depender de la vista: cupo, duplicados,
creación de Persona, resolución del trámite y comunicación con Moodle.
La vista sólo traduce las excepciones a errores de formulario o mensajes.
"""
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import Persona, PeriodoPlan

from .correos import CorreoSIGA
from .cupos import tiene_cupo
from .models import DocumentoPreinscripcion, Preinscripcion
from .moodle import ClienteMoodle


class CupoAgotado(Exception):
    """La oferta ya no tiene cupos disponibles."""


class SolicitudDuplicada(Exception):
    """La persona ya tiene una solicitud activa para ese plan."""


class SolicitudYaResuelta(Exception):
    """La solicitud ya fue aceptada o rechazada por otra persona."""


class MotivoRequerido(Exception):
    """El rechazo necesita un motivo."""


@transaction.atomic
def registrar_preinscripcion(*, datos, archivos):
    """Registra una preinscripción completa o no registra nada.

    Bloquea la oferta para serializar las altas de esa carrera, revalida el
    cupo dentro del lock y convierte la violación de la constraint
    `una_preinscripcion_activa_por_plan` en SolicitudDuplicada.
    """
    # El lock sobre la oferta hace que dos envíos simultáneos para la misma
    # carrera se ejecuten uno después del otro y no puedan superar el cupo.
    oferta = PeriodoPlan.objects.select_for_update().get(pk=datos["oferta"].pk)
    if not tiene_cupo(oferta):
        raise CupoAgotado

    persona = Persona.objects.filter(dni=datos["dni"]).first()
    if persona is None:
        try:
            # Transacción anidada: si otra petición creó la misma persona
            # entre el SELECT y el INSERT, se recupera la fila existente.
            with transaction.atomic():
                persona = Persona.objects.create(
                    dni=datos["dni"],
                    nombre=datos["nombre"].strip(),
                    apellido=datos["apellido"].strip(),
                    fecha_nacimiento=datos["fecha_nacimiento"],
                    email=datos["email"].lower(),
                    telefono=datos["telefono"].strip(),
                )
        except IntegrityError:
            # Otra petición creó la misma persona al mismo tiempo.
            persona = Persona.objects.get(dni=datos["dni"])

    try:
        with transaction.atomic():
            preinscripcion = Preinscripcion.objects.create(
                persona=persona,
                periodo_plan=oferta,
                # Se guarda una copia de lo declarado sin sobrescribir Persona.
                datos_declarados={
                    "nombre": datos["nombre"].strip(),
                    "apellido": datos["apellido"].strip(),
                    "dni": datos["dni"],
                    "fecha_nacimiento": datos["fecha_nacimiento"].isoformat(),
                    "email": datos["email"].lower(),
                    "telefono": datos["telefono"].strip(),
                    "oferta_id": oferta.pk,
                },
            )
    except IntegrityError as error:
        # La constraint de la base es la última defensa contra dos envíos
        # simultáneos con el mismo DNI. Se traduce a un error de formulario.
        if "una_preinscripcion_activa_por_plan" in str(error):
            raise SolicitudDuplicada from error
        raise

    # Los documentos van dentro de la misma transacción del alta.
    for tipo, archivo in archivos.items():
        if archivo:
            DocumentoPreinscripcion.objects.create(
                preinscripcion=preinscripcion,
                tipo=tipo,
                archivo=archivo,
                nombre_original=archivo.name,
            )

    return preinscripcion


@dataclass(frozen=True)
class ResultadoAceptacion:
    solicitud: Preinscripcion
    clave_temporal: str | None
    cuenta_existente: bool
    correo_enviado: bool
    error_correo: str = ""


@dataclass(frozen=True)
class ResultadoRechazo:
    solicitud: Preinscripcion
    correo_enviado: bool
    error_correo: str = ""


class GestorSolicitudes:
    """Resuelve aceptar y rechazar sin depender de HTTP ni de mensajes.

    Las dependencias externas (Moodle y correo) se inyectan, así que el flujo
    completo se puede probar con dobles sin tocar la red ni el SMTP.
    """

    def __init__(self, moodle=None, correo=None):
        self.moodle = moodle or ClienteMoodle()
        self.correo = correo or CorreoSIGA()

    def aceptar(self, solicitud, usuario, observaciones=""):
        """Primero Moodle, después el estado.

        Si Moodle falla, la excepción sale antes de la transacción y la
        solicitud sigue pendiente. La fila se bloquea y se revalida después
        de hablar con Moodle, porque mientras tanto otra persona pudo
        resolver la misma solicitud.
        """
        if not solicitud.esta_pendiente:
            raise SolicitudYaResuelta("La solicitud ya estaba resuelta.")

        persona = solicitud.persona
        clave_temporal = self.moodle.crear_usuario(persona)
        cuenta_existente = clave_temporal is None

        with transaction.atomic():
            actual = (
                Preinscripcion.objects.select_for_update()
                .select_related("persona")
                .get(pk=solicitud.pk)
            )
            if not actual.esta_pendiente:
                raise SolicitudYaResuelta(
                    "Otra persona resolvió esta solicitud mientras la procesabas."
                )
            try:
                actual.aceptar(usuario, observaciones)
            except ValueError as error:
                raise SolicitudYaResuelta(str(error)) from error

            actual.moodle_estado = Preinscripcion.MoodleEstado.CREADO
            actual.moodle_error = ""
            actual.moodle_actualizado = timezone.now()
            actual.save(update_fields=["moodle_estado", "moodle_error", "moodle_actualizado"])

        ok, error = self.correo.aceptacion(
            actual,
            persona.dni if clave_temporal else None,
            clave_temporal,
            cuenta_moodle_existente=cuenta_existente,
        )
        return ResultadoAceptacion(actual, clave_temporal, cuenta_existente, ok, error)

    def rechazar(self, solicitud, usuario, motivo):
        """Rechaza con motivo. El correo se envía después del commit."""
        motivo = (motivo or "").strip()
        if not motivo:
            raise MotivoRequerido("Para rechazar hay que indicar el motivo.")

        with transaction.atomic():
            actual = (
                Preinscripcion.objects.select_for_update()
                .select_related("persona")
                .get(pk=solicitud.pk)
            )
            if not actual.esta_pendiente:
                raise SolicitudYaResuelta("La solicitud ya estaba resuelta.")
            try:
                actual.rechazar(usuario, motivo)
            except ValueError as error:
                raise SolicitudYaResuelta(str(error)) from error

        ok, error = self.correo.rechazo(actual)
        return ResultadoRechazo(actual, ok, error)