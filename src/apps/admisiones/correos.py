"""
Correos al aspirante.

En desarrollo se imprimen en la consola (docker compose logs -f web).
Si el envío falla, se registra el error pero no se interrumpe el trámite:
la solicitud ya quedó guardada.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

def enviar_recepcion(preinscripcion):
    return _enviar(preinscripcion, f"Recibimos tu solicitud {preinscripcion.numero}", "recepcion")


def enviar_aceptacion(preinscripcion, usuario_moodle=None, clave_moodle=None, cuenta_moodle_existente=False):
    return _enviar(
        preinscripcion,
        "Tu preinscripción fue aceptada",
        "aceptacion",
        usuario_moodle=usuario_moodle,
        clave_moodle=clave_moodle,
        cuenta_moodle_existente=cuenta_moodle_existente,
    )


def enviar_rechazo(preinscripcion):
    return _enviar(preinscripcion, "Tu preinscripción no fue aceptada", "rechazo")



def _enviar(preinscripcion, asunto, plantilla, **datos_adicionales):
    """Envía un correo y devuelve (ok, error).
    No propaga la excepción: las vistas necesitan saber si el correo salió
    para informarlo, sin deshacer la operación ya confirmada. El error se
    deja igualmente en el log."""
    contexto = {"p": preinscripcion, "sitio": settings.SITE_URL.rstrip("/")}
    contexto.update(datos_adicionales)
    try:
        send_mail(
            subject=f"SIGA · {asunto}",
            message=render_to_string(f"emails/{plantilla}.txt", contexto),
            html_message=render_to_string(f"emails/{plantilla}.html", contexto),
            from_email=None,  # usa DEFAULT_FROM_EMAIL
            recipient_list=[preinscripcion.persona.email],
        )
        return True, ""
    except Exception as error:
        logger.exception("No se pudo enviar el correo de %s", preinscripcion.numero)
        return False, str(error)


class CorreoSIGA:
    """Adaptador de los correos del trámite.

    Permite inyectar un notificador falso en los tests del gestor, sin
    parchear funciones globales.
    """

    def recepcion(self, solicitud):
        return enviar_recepcion(solicitud)

    def aceptacion(
        self,
        solicitud,
        usuario_moodle=None,
        clave_moodle=None,
        cuenta_moodle_existente=False,
    ):
        return enviar_aceptacion(
            solicitud,
            usuario_moodle,
            clave_moodle,
            cuenta_moodle_existente=cuenta_moodle_existente,
        )

    def rechazo(self, solicitud):
        return enviar_rechazo(solicitud)
