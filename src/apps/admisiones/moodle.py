"""Integración con el servicio REST de Moodle."""
import json
import logging
import secrets
import string
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class MoodleIntegrationError(Exception):
    """Error al crear o confirmar una cuenta en Moodle."""


def crear_usuario_moodle(persona):
    """Crea una sola cuenta por persona y devuelve su clave temporal si es nueva."""
    if persona.moodle_user_id:
        return None
    if not settings.MOODLE_API_TOKEN:
        raise MoodleIntegrationError("Falta configurar MOODLE_API_TOKEN.")

    clave_temporal = _generar_clave_temporal()
    datos = {
        "wstoken": settings.MOODLE_API_TOKEN,
        "wsfunction": "core_user_create_users",
        "moodlewsrestformat": "json",
        "users[0][username]": persona.dni,
        "users[0][password]": clave_temporal,
        "users[0][firstname]": persona.nombre,
        "users[0][lastname]": persona.apellido,
        "users[0][email]": persona.email,
        "users[0][auth]": "manual",
        "users[0][idnumber]": persona.dni,
        "users[0][preferences][0][type]": "auth_forcepasswordchange",
        "users[0][preferences][0][value]": "1",
    }
    solicitud = Request(
        f"{settings.MOODLE_URL}/webservice/rest/server.php",
        data=urlencode(datos).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": settings.MOODLE_HOST_HEADER,
        },
        method="POST",
    )

    try:
        with urlopen(solicitud, timeout=10) as respuesta:
            cuerpo = respuesta.read()
    except HTTPError as error:
        raise MoodleIntegrationError(f"Moodle respondió con HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        logger.exception("No se pudo conectar con Moodle.")
        raise MoodleIntegrationError("No se pudo conectar con Moodle.") from error

    try:
        resultado = json.loads(cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MoodleIntegrationError("Moodle devolvió una respuesta inválida.") from error

    if isinstance(resultado, dict) and resultado.get("exception"):
        codigo = resultado.get("errorcode", "error")
        mensaje = resultado.get("message", "Moodle rechazó la creación de la cuenta.")
        raise MoodleIntegrationError(f"Moodle ({codigo}): {mensaje}")
    if not isinstance(resultado, list) or not resultado or not isinstance(resultado[0], dict):
        raise MoodleIntegrationError("Moodle no confirmó la creación de la cuenta.")
    try:
        moodle_user_id = int(resultado[0]["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise MoodleIntegrationError("Moodle no confirmó la creación de la cuenta.") from error
    if moodle_user_id <= 0:
        raise MoodleIntegrationError("Moodle devolvió un ID de usuario inválido.")

    persona.moodle_user_id = moodle_user_id
    persona.save(update_fields=["moodle_user_id", "actualizado"])
    return clave_temporal


def _generar_clave_temporal():
    mayusculas = string.ascii_uppercase
    minusculas = string.ascii_lowercase
    numeros = string.digits
    especiales = "!@#$%"
    alfabeto = mayusculas + minusculas + numeros + especiales
    caracteres = [
        secrets.choice(mayusculas),
        secrets.choice(minusculas),
        secrets.choice(numeros),
        secrets.choice(especiales),
        *(secrets.choice(alfabeto) for _ in range(12)),
    ]
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)
