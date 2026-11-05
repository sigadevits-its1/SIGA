"""Integración con el servicio REST de Moodle.

El acceso HTTP vive en `ClienteMoodle`. Las funciones del final son
envoltorios compatibles con el código anterior: delegan en una instancia
nueva del cliente.
"""
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


class ClienteMoodle:
    """Cliente del servicio web de Moodle.

    Concentra token, URL y timeout. Cada método devuelve datos ya validados
    o lanza MoodleIntegrationError; nunca expone respuestas crudas.
    """

    def __init__(self, token=None, url=None, host_header=None, timeout=10):
        # token=None significa "leer de settings". token="" es un token vacío
        # y debe fallar, no caer en silencio en la configuración.
        self.token = settings.MOODLE_API_TOKEN if token is None else token
        self.url = (url or settings.MOODLE_URL).rstrip("/")
        self.host_header = host_header or settings.MOODLE_HOST_HEADER
        self.timeout = timeout

    # --- API pública ---------------------------------------------------

    def buscar_por_dni(self, dni):
        """Devuelve el ID de Moodle si el usuario ya existe, o None.

        Moodle devuelve una lista vacía cuando no encuentra el DNI. Algunas
        versiones responden `invalidparameter`; también se considera que la
        cuenta no existe.
        """
        self._exigir_token()
        resultado = self._llamar(
            "core_user_get_users_by_field",
            {"field": "username", "values[0]": dni},
        )
        if self._es_error(resultado):
            if resultado.get("errorcode") == "invalidparameter":
                return None
            raise MoodleIntegrationError(resultado.get("message", "Error al consultar Moodle."))

        if not resultado:
            return None
        try:
            return int(resultado[0]["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise MoodleIntegrationError("Moodle devolvió un usuario inválido.") from error

    def crear_usuario(self, persona):
        """Crea la cuenta o vincula la existente.

        Devuelve la clave temporal sólo si la cuenta se creó en esta llamada.
        Si ya existía (buscada por DNI), vincula el ID y devuelve None: SIGA
        no puede recuperar una clave que no generó.
        """
        if persona.moodle_user_id:
            return None
        self._exigir_token()

        existente = self.buscar_por_dni(persona.dni)
        if existente:
            self._vincular(persona, existente)
            return None

        clave = _generar_clave_temporal()
        resultado = self._llamar("core_user_create_users", {
            "users[0][username]": persona.dni,
            "users[0][password]": clave,
            "users[0][firstname]": persona.nombre,
            "users[0][lastname]": persona.apellido,
            "users[0][email]": persona.email,
            "users[0][auth]": "manual",
            "users[0][idnumber]": persona.dni,
            "users[0][preferences][0][type]": "auth_forcepasswordchange",
            "users[0][preferences][0][value]": "1",
        })
        if self._es_error(resultado):
            codigo = resultado.get("errorcode", "error")
            mensaje = resultado.get("message", "Moodle rechazó la creación de la cuenta.")
            raise MoodleIntegrationError(f"Moodle ({codigo}): {mensaje}")
        if not isinstance(resultado, list) or not resultado or not isinstance(resultado[0], dict):
            raise MoodleIntegrationError("Moodle no confirmó la creación de la cuenta.")
        try:
            moodle_id = int(resultado[0]["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise MoodleIntegrationError("Moodle no confirmó la creación de la cuenta.") from error
        if moodle_id <= 0:
            raise MoodleIntegrationError("Moodle devolvió un ID de usuario inválido.")

        self._vincular(persona, moodle_id)
        return clave

    def restablecer_clave(self, persona):
        """Genera una clave nueva para una cuenta ya vinculada."""
        if not persona.moodle_user_id:
            raise MoodleIntegrationError("La persona no tiene cuenta de Moodle.")
        self._exigir_token()

        clave = _generar_clave_temporal()
        resultado = self._llamar("core_user_update_users", {
            "users[0][id]": persona.moodle_user_id,
            "users[0][password]": clave,
        })
        if self._es_error(resultado):
            raise MoodleIntegrationError(resultado.get("message", "Moodle rechazó el cambio de clave."))
        return clave

    # --- Infraestructura ------------------------------------------------

    def _exigir_token(self):
        if not self.token:
            raise MoodleIntegrationError("Falta configurar MOODLE_API_TOKEN.")

    def _llamar(self, funcion, parametros):
        """POST a server.php y devuelve el JSON decodificado.

        No interpreta errores de negocio: cada método decide qué hacer con
        `exception` y `errorcode`.
        """
        datos = {
            "wstoken": self.token,
            "wsfunction": funcion,
            "moodlewsrestformat": "json",
            **parametros,
        }
        solicitud = Request(
            f"{self.url}/webservice/rest/server.php",
            data=urlencode(datos).encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": self.host_header,
            },
            method="POST",
        )
        try:
            with urlopen(solicitud, timeout=self.timeout) as respuesta:
                cuerpo = respuesta.read()
        except HTTPError as error:
            raise MoodleIntegrationError(f"Moodle respondió con HTTP {error.code}.") from error
        except (URLError, TimeoutError) as error:
            logger.exception("No se pudo conectar con Moodle.")
            raise MoodleIntegrationError("No se pudo conectar con Moodle.") from error

        try:
            return json.loads(cuerpo.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MoodleIntegrationError("Moodle devolvió una respuesta inválida.") from error

    @staticmethod
    def _es_error(resultado):
        return isinstance(resultado, dict) and bool(resultado.get("exception"))

    @staticmethod
    def _vincular(persona, moodle_id):
        persona.moodle_user_id = moodle_id
        persona.save(update_fields=["moodle_user_id", "actualizado"])


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


# --- Compatibilidad con el código anterior ------------------------------

def crear_usuario_moodle(persona):
    return ClienteMoodle().crear_usuario(persona)


def buscar_usuario_moodle(dni):
    return ClienteMoodle().buscar_por_dni(dni)


def restablecer_clave_moodle(persona):
    return ClienteMoodle().restablecer_clave(persona)
