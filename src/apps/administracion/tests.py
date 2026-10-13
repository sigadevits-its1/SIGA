import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from django.utils import timezone

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


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
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
        for url in [reverse("administracion:bandeja"), reverse("administracion:documento", args=[self.doc.pk])]:
            self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_sin_rol_administrativo_da_403(self):
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(reverse("administracion:bandeja")).status_code, 403)
        self.assertEqual(self.client.get(reverse("administracion:documento", args=[self.doc.pk])).status_code, 403)

    def test_bandeja_y_ficha_con_rol(self):
        self.client.force_login(self.secretaria)
        self.assertContains(self.client.get(reverse("administracion:bandeja")), "Sofía Martínez")
        self.assertContains(self.client.get(reverse("administracion:bandeja"), {"q": "46318"}), "Sofía Martínez")
        self.assertContains(self.client.get(reverse("administracion:ficha", args=[self.p.pk])), self.p.numero)
        self.assertEqual(self.client.get(reverse("administracion:documento", args=[self.doc.pk])).status_code, 200)

    def test_aceptar(self):
        self.client.force_login(self.secretaria)
        self.client.post(reverse("administracion:aceptar", args=[self.p.pk]))
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.ACEPTADO)
        self.assertEqual(self.p.revisor, self.secretaria)
        self.assertIsNotNone(self.p.fecha_revision)
        self.assertEqual(len(mail.outbox), 1)

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
        self.client.post(reverse("administracion:aceptar", args=[self.p.pk]))
        self.client.post(reverse("administracion:rechazar", args=[self.p.pk]), {"motivo": "x"})
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, Preinscripcion.Estado.ACEPTADO)
