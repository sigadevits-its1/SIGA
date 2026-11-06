import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from django.utils import timezone

from apps.admisiones.moodle import MoodleIntegrationError
from apps.admisiones.models import DocumentoPreinscripcion, Preinscripcion
from apps.core.models import Carrera, PeriodoInscripcion, PeriodoPlan, Persona, PlanCarrera

from .permisos import GRUPO_ADMINISTRATIVO

MEDIA_TEMPORAL = tempfile.mkdtemp()


def crear_oferta():
    ahora = timezone.now()
    periodo = PeriodoInscripcion.objects.create(
        codigo="ING-TEST", nombre="Ingreso test", ciclo_lectivo=2027,
        fecha_desde=ahora - timedelta(days=1), fecha_hasta=ahora + timedelta(days=1),
    )
    carrera = Carrera.objects.create(codigo="TSADSI", nombre="Análisis de Sistemas", nombre_corto="Sistemas")
    plan = PlanCarrera.objects.create(carrera=carrera, codigo="P1", nombre="Plan 1")
    return PeriodoPlan.objects.create(periodo=periodo, plan=plan, cupo_ingresantes=10)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL, MOODLE_ACTIVO=True)
class PanelAdministrativoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        persona = Persona.objects.create(
            nombre="Sofía", apellido="Martínez", dni="46318765", fecha_nacimiento="2006-08-18",
            email="sofia@example.com", telefono="123456789",
        )
        self.p = Preinscripcion.objects.create(persona=persona, periodo_plan=crear_oferta())
        self.doc = DocumentoPreinscripcion(preinscripcion=self.p, tipo="dni", nombre_original="dni.pdf")
        self.doc.archivo.save("dni.pdf", ContentFile(b"%PDF-1.4"), save=True)

        self.secretaria = User.objects.create_user("secretaria", password="x")
        self.secretaria.groups.add(Group.objects.get(name=GRUPO_ADMINISTRATIVO))
        self.otro = User.objects.create_user("otro", password="x")

    def test_sin_sesion_redirige_al_login(self):
        for url in [
            reverse("administracion:bandeja"),
            reverse("administracion:aprobados_pdf"),
            reverse("administracion:documento", args=[self.doc.pk]),
        ]:
            self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_sin_rol_administrativo_da_403(self):
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(reverse("administracion:bandeja")).status_code, 403)
        self.assertEqual(self.client.get(reverse("administracion:aprobados_pdf")).status_code, 403)
        self.assertEqual(self.client.get(reverse("administracion:documento", args=[self.doc.pk])).status_code, 403)

    def test_bandeja_y_ficha_con_rol(self):
        self.client.force_login(self.secretaria)
        self.assertContains(self.client.get(reverse("administracion:bandeja")), "Sofía Martínez")
        self.assertContains(self.client.get(reverse("administracion:bandeja"), {"q": "46318"}), "Sofía Martínez")
        self.assertContains(self.client.get(reverse("administracion:ficha", args=[self.p.pk])), self.p.numero)
        self.assertEqual(self.client.get(reverse("administracion:documento", args=[self.doc.pk])).status_code, 200)
        for modulo in ("carreras", "periodos", "usuarios"):
            respuesta = self.client.get(reverse("administracion:en_construccion", args=[modulo]))
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "Módulo en construcción")
        self.assertRedirects(
            self.client.get("/admin/core/carrera/"),
            reverse("administracion:en_construccion", args=["carreras"]),
        )

    def test_aceptar(self):
        self.client.force_login(self.secretaria)
        with patch("apps.admisiones.moodle.ClienteMoodle.crear_usuario", return_value="ClaveTemporal123!") as crear:
            self.client.post(
                reverse("administracion:aceptar", args=[self.p.pk]),
                {"observaciones": "Documentación verificada"},
            )
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.ACEPTADO)
        self.assertEqual(self.p.revisor, self.secretaria)
        self.assertIsNotNone(self.p.fecha_revision)
        self.assertEqual(len(mail.outbox), 1)
        crear.assert_called_once_with(self.p.persona)
        self.assertIn("Usuario: 46318765", mail.outbox[0].body)
        self.assertIn("Clave temporal: ClaveTemporal123!", mail.outbox[0].body)
        self.assertIn("cambies la clave", mail.outbox[0].body)

    def test_falla_moodle_y_no_acepta_la_solicitud(self):
        self.client.force_login(self.secretaria)
        with patch(
            "apps.admisiones.moodle.ClienteMoodle.crear_usuario",
            side_effect=MoodleIntegrationError("Falta configurar MOODLE_API_TOKEN."),
        ):
            respuesta = self.client.post(reverse("administracion:aceptar", args=[self.p.pk]))
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.PENDIENTE)
        self.assertEqual(len(mail.outbox), 0)
        self.assertRedirects(respuesta, reverse("administracion:ficha", args=[self.p.pk]))

    @override_settings(MOODLE_ACTIVO=False)
    def test_aceptar_con_moodle_desactivado_no_hace_peticiones(self):
        self.client.force_login(self.secretaria)
        with patch("apps.admisiones.moodle.ClienteMoodle.crear_usuario") as crear:
            self.client.post(
                reverse("administracion:aceptar", args=[self.p.pk]),
                {"observaciones": "Aceptado sin integración Moodle"},
            )
        crear.assert_not_called()
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.ACEPTADO)
        self.assertEqual(self.p.moodle_estado, Preinscripcion.MoodleEstado.PENDIENTE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn("Clave temporal:", mail.outbox[0].body)

    def test_rechazar_exige_motivo_y_envia_correo(self):
        self.client.force_login(self.secretaria)
        url = reverse("administracion:rechazar", args=[self.p.pk])
        self.client.post(url, {"motivo": "  "})
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.PENDIENTE)

        self.client.post(url, {"motivo": "El DNI no se lee."})
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.RECHAZADO)
        self.assertIn("El DNI no se lee.", mail.outbox[0].body)
        self.assertIn("/preinscripcion/", mail.outbox[0].body)

    def test_no_se_puede_resolver_dos_veces(self):
        self.client.force_login(self.secretaria)
        with patch("apps.admisiones.moodle.ClienteMoodle.crear_usuario", return_value="ClaveTemporal123!"):
            self.client.post(reverse("administracion:aceptar", args=[self.p.pk]))
        self.client.post(reverse("administracion:rechazar", args=[self.p.pk]), {"motivo": "x"})
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.ACEPTADO)

    def test_exportar_pdf_aprobados_incluye_solo_aceptados(self):
        self.client.force_login(self.secretaria)
        # Creamos un segundo aspirante pendiente y un tercero rechazado
        pendiente = Persona.objects.create(
            nombre="Lucas", apellido="Gomez", dni="45102334", fecha_nacimiento="2005-03-10",
            email="lucas@example.com", telefono="2920111222",
        )
        Preinscripcion.objects.create(persona=pendiente, periodo_plan=self.p.periodo_plan)

        rechazado = Persona.objects.create(
            nombre="Valentina", apellido="Ruiz", dni="47020118", fecha_nacimiento="2006-11-22",
            email="valentina@example.com", telefono="2920333444",
        )
        sol_rechazada = Preinscripcion.objects.create(persona=rechazado, periodo_plan=self.p.periodo_plan)
        sol_rechazada.rechazar(self.secretaria, "Falta dorso del DNI")

        # Aceptamos a Sofía Martínez
        self.p.aceptar(self.secretaria, "OK")

        respuesta = self.client.get(reverse("administracion:aprobados_pdf"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn("inscriptos_aprobados_ing-test.pdf", respuesta["Content-Disposition"])
        self.assertTrue(respuesta.content.startswith(b"%PDF-1.4"))
        self.assertTrue(respuesta.content.rstrip().endswith(b"%%EOF"))

        # Debe incluir a la aspirante aceptada (Sofía Martínez) y excluir pendientes/rechazados
        self.assertIn(b"46318765", respuesta.content)
        self.assertIn(self.p.numero.encode("ascii"), respuesta.content)
        self.assertNotIn(b"45102334", respuesta.content)
        self.assertNotIn(b"47020118", respuesta.content)

