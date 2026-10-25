from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

from django.core import mail
from django.test import SimpleTestCase, override_settings

from .correos import enviar_aceptacion, enviar_recepcion, enviar_rechazo
from .moodle import MoodleIntegrationError, crear_usuario_moodle


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://siga.example.com/",
)
class CorreosTests(SimpleTestCase):
    def setUp(self):
        self.preinscripcion = SimpleNamespace(
            numero="PRE-2027-00005",
            persona=SimpleNamespace(nombre="Sofía", email="sofia@example.com"),
            periodo_plan=SimpleNamespace(
                plan=SimpleNamespace(carrera=SimpleNamespace(
                    nombre="Tecnicatura Superior en Administración Pública",
                )),
                periodo=SimpleNamespace(nombre="Ingreso 2027"),
            ),
            observaciones="",
        )

    def test_los_tres_correos_envian_texto_y_html_con_los_datos(self):
        for enviar in (enviar_recepcion, enviar_aceptacion, enviar_rechazo):
            with self.subTest(enviar=enviar.__name__):
                enviar(self.preinscripcion)
                correo = mail.outbox[-1]
                self.assertEqual(correo.to, ["sofia@example.com"])
                self.assertTrue(correo.subject.startswith("SIGA · "))
                self.assertIn("Sofía", correo.body)
                self.assertIn(self.preinscripcion.numero, correo.body)
                self.assertEqual(len(correo.alternatives), 1)
                html, tipo = correo.alternatives[0]
                self.assertEqual(tipo, "text/html")
                for dato in (
                    "Sofía", self.preinscripcion.numero,
                    self.preinscripcion.periodo_plan.plan.carrera.nombre,
                    "Ingreso 2027", "Secretaría · ITS N.º 1",
                ):
                    self.assertIn(dato, html)
                mensaje = correo.message()
                self.assertEqual(mensaje.get_content_type(), "multipart/alternative")
                self.assertEqual(
                    [parte.get_content_type() for parte in mensaje.get_payload()],
                    ["text/plain", "text/html"],
                )

    def test_recepcion_informa_revision_sin_mostrar_observaciones(self):
        self.preinscripcion.observaciones = "Nota interna de revisión"
        enviar_recepcion(self.preinscripcion)
        html = mail.outbox[0].alternatives[0].content
        self.assertIn("Solicitud recibida", html)
        self.assertIn("Secretaría va a revisar tu solicitud", html)
        self.assertNotIn(self.preinscripcion.observaciones, html)

    def test_aceptacion_sin_observaciones(self):
        enviar_aceptacion(self.preinscripcion)
        html = mail.outbox[0].alternatives[0].content
        self.assertIn("Preinscripción aceptada", html)
        self.assertIn("información de inicio de clases", html)
        self.assertNotIn("Observaciones de secretaría", html)

    def test_aceptacion_envia_credenciales_de_moodle_en_texto_y_html(self):
        enviar_aceptacion(self.preinscripcion, "46318765", "ClaveTemporal123!")
        correo = mail.outbox[0]
        self.assertIn("Usuario: 46318765", correo.body)
        self.assertIn("Clave temporal: ClaveTemporal123!", correo.body)
        self.assertIn("Usuario:</strong> 46318765", correo.alternatives[0].content)
        self.assertIn("Clave temporal:</strong> ClaveTemporal123!", correo.alternatives[0].content)
        self.assertIn("Moodle te pedirá que cambies la clave", correo.body)

    def test_observaciones_conservan_saltos_y_escapan_html(self):
        self.preinscripcion.persona.nombre = "Sofía <img src=x>"
        self.preinscripcion.observaciones = "Traé el original.\n<script>alert('x')</script>"
        for enviar in (enviar_aceptacion, enviar_rechazo):
            with self.subTest(enviar=enviar.__name__):
                enviar(self.preinscripcion)
                html = mail.outbox[-1].alternatives[0].content
                self.assertIn("Sofía &lt;img src=x&gt;", html)
                self.assertIn("Traé el original.<br>&lt;script&gt;", html)
                self.assertNotIn("<script>", html)
                self.assertNotIn("<img src=x>", html)
                self.assertIn(self.preinscripcion.observaciones, mail.outbox[-1].body)

    def test_rechazo_muestra_motivo_y_enlace_al_formulario(self):
        self.preinscripcion.observaciones = "El DNI no se lee."
        enviar_rechazo(self.preinscripcion)
        correo = mail.outbox[0]
        html = correo.alternatives[0].content
        self.assertIn("Motivo del rechazo", html)
        self.assertIn(self.preinscripcion.observaciones, html)
        self.assertIn("Volver a preinscribirme", html)
        self.assertIn('href="https://siga.example.com/preinscripcion/"', html)
        self.assertIn("https://siga.example.com/preinscripcion/", correo.body)
        self.assertNotIn("siga.example.com//", html)


@override_settings(
    MOODLE_URL="http://localhost:8080",
    MOODLE_API_TOKEN="token-de-prueba",
)
class MoodleTests(SimpleTestCase):
    def test_crea_usuario_con_dni_y_solicita_cambio_de_clave(self):
        persona = SimpleNamespace(
            dni="46318765",
            nombre="Sofía",
            apellido="Martínez",
            email="sofia@example.com",
            moodle_user_id=None,
            save=Mock(),
        )
        respuesta = BytesIO(b'[{"id":17,"username":"46318765"}]')
        with patch("apps.admisiones.moodle.urlopen", return_value=respuesta) as urlopen:
            clave = crear_usuario_moodle(persona)

        self.assertEqual(len(clave), 16)
        solicitud = urlopen.call_args.args[0]
        parametros = parse_qs(solicitud.data.decode("utf-8"))
        self.assertEqual(solicitud.full_url, "http://localhost:8080/webservice/rest/server.php")
        self.assertEqual(parametros["wsfunction"], ["core_user_create_users"])
        self.assertEqual(parametros["users[0][username]"], ["46318765"])
        self.assertEqual(parametros["users[0][idnumber]"], ["46318765"])
        self.assertEqual(parametros["users[0][password]"], [clave])
        self.assertEqual(parametros["users[0][preferences][0][type]"], ["auth_forcepasswordchange"])
        self.assertEqual(parametros["users[0][preferences][0][value]"], ["1"])
        self.assertEqual(persona.moodle_user_id, 17)
        persona.save.assert_called_once_with(update_fields=["moodle_user_id", "actualizado"])

    def test_no_duplica_una_cuenta_ya_vinculada(self):
        persona = SimpleNamespace(moodle_user_id=17)
        with patch("apps.admisiones.moodle.urlopen") as urlopen:
            clave = crear_usuario_moodle(persona)
        self.assertIsNone(clave)
        urlopen.assert_not_called()

    @override_settings(MOODLE_API_TOKEN="")
    def test_exige_token_de_moodle(self):
        persona = SimpleNamespace(
            dni="46318765",
            nombre="Sofía",
            apellido="Martínez",
            email="sofia@example.com",
            moodle_user_id=None,
        )
        with self.assertRaisesMessage(MoodleIntegrationError, "Falta configurar MOODLE_API_TOKEN."):
            crear_usuario_moodle(persona)
