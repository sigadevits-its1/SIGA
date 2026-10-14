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
    _enviar(preinscripcion, f"Recibimos tu solicitud {preinscripcion.numero}", "recepcion")


def enviar_aceptacion(preinscripcion):
    _enviar(preinscripcion, "Tu preinscripción fue aceptada", "aceptacion")


def enviar_rechazo(preinscripcion):
    _enviar(preinscripcion, "Tu preinscripción no fue aceptada", "rechazo")


def _enviar(preinscripcion, asunto, plantilla):
    contexto = {"p": preinscripcion, "sitio": settings.SITE_URL.rstrip("/")}
    try:
        send_mail(
            subject=f"SIGA · {asunto}",
            message=render_to_string(f"emails/{plantilla}.txt", contexto),
            html_message=render_to_string(f"emails/{plantilla}.html", contexto),
            from_email=None,  # usa DEFAULT_FROM_EMAIL
            recipient_list=[preinscripcion.persona.email],
        )
    except Exception:
        logger.exception("No se pudo enviar el correo de %s", preinscripcion.numero)
