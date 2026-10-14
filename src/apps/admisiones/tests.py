from types import SimpleNamespace

from django.core import mail
from django.test import SimpleTestCase, override_settings

from .correos import enviar_aceptacion, enviar_recepcion, enviar_rechazo


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
