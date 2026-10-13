import shutil
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.admisiones.models import Preinscripcion
from apps.core.models import Carrera, PeriodoInscripcion, PeriodoPlan, PlanCarrera

MEDIA_TEMPORAL = tempfile.mkdtemp()


def pdf(nombre="doc.pdf", tamanio=100):
    return SimpleUploadedFile(nombre, b"%PDF-1.4" + b"0" * tamanio, content_type="application/pdf")


def crear_oferta(cupo=10, codigo="TSADSI"):
    ahora = timezone.now()
    periodo, _ = PeriodoInscripcion.objects.get_or_create(
        codigo="ING-TEST",
        defaults=dict(nombre="Ingreso test", ciclo_lectivo=2027,
                      fecha_desde=ahora - timedelta(days=1), fecha_hasta=ahora + timedelta(days=1)),
    )
    carrera = Carrera.objects.create(codigo=codigo, nombre=f"Carrera {codigo}", nombre_corto=codigo)
    plan = PlanCarrera.objects.create(carrera=carrera, codigo="P1", nombre="Plan 1")
    return PeriodoPlan.objects.create(periodo=periodo, plan=plan, cupo_ingresantes=cupo)


@override_settings(MEDIA_ROOT=MEDIA_TEMPORAL)
class FormularioPreinscripcionTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEMPORAL, ignore_errors=True)

    def setUp(self):
        self.oferta = crear_oferta()
        self.url = reverse("preinscripcion:formulario")

    def datos(self, **cambios):
        datos = {
            "nombre": "Sofía", "apellido": "Martínez", "dni": "46318765",
            "fecha_nacimiento": "2006-08-18", "email": "sofia@example.com",
            "email_confirmacion": "sofia@example.com", "telefono": "+54 9 2920 462187",
            "oferta": self.oferta.pk, "titulo_situacion": "titulo",
            "archivo_dni": pdf(), "archivo_titulo": pdf(),
            "declaracion": "on", "privacidad": "on",
        }
        datos.update(cambios)
        return datos

    def test_envio_valido_crea_la_solicitud_y_manda_correo(self):
        respuesta = self.client.post(self.url, self.datos())
        self.assertRedirects(respuesta, reverse("preinscripcion:enviada"))
        p = Preinscripcion.objects.get()
        self.assertEqual(p.estado, Preinscripcion.Estado.PENDIENTE)
        self.assertEqual(sorted(p.documentos.values_list("tipo", flat=True)), ["dni", "titulo"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(p.numero, mail.outbox[0].subject)

    def test_constancia_en_tramite_y_analitico_opcional(self):
        self.client.post(self.url, self.datos(titulo_situacion="titulo_en_tramite", archivo_analitico=pdf()))
        tipos = sorted(Preinscripcion.objects.get().documentos.values_list("tipo", flat=True))
        self.assertEqual(tipos, ["analitico", "dni", "titulo_en_tramite"])

    def test_titulo_o_constancia_es_obligatorio(self):
        datos = self.datos()
        del datos["archivo_titulo"]
        self.client.post(self.url, datos)
        self.assertFalse(Preinscripcion.objects.exists())

    def test_rechaza_formato_y_tamanio_invalidos(self):
        exe = SimpleUploadedFile("virus.exe", b"MZ")
        self.client.post(self.url, self.datos(archivo_dni=exe))
        with self.settings(MAX_TAMANIO_DOCUMENTO=50):
            self.client.post(self.url, self.datos(archivo_dni=pdf(tamanio=100)))
        self.assertFalse(Preinscripcion.objects.exists())

    def test_carrera_sin_cupo_no_se_puede_elegir(self):
        self.oferta.cupo_ingresantes = 0
        self.oferta.save()
        respuesta = self.client.post(self.url, self.datos())
        self.assertContains(respuesta, "no tiene cupo")
        self.assertFalse(Preinscripcion.objects.exists())

    def test_no_permite_dos_solicitudes_activas_en_el_periodo(self):
        self.client.post(self.url, self.datos())
        otra = crear_oferta(codigo="TSAP")
        self.client.post(self.url, self.datos(oferta=otra.pk))
        self.assertEqual(Preinscripcion.objects.count(), 1)

    def test_si_fue_rechazado_puede_volver_a_enviar(self):
        self.client.post(self.url, self.datos())
        Preinscripcion.objects.update(estado=Preinscripcion.Estado.RECHAZADO)
        self.client.post(self.url, self.datos())
        self.assertEqual(Preinscripcion.objects.count(), 2)

    def test_campo_trampa_bloquea_robots(self):
        self.client.post(self.url, self.datos(website="http://spam"))
        self.assertFalse(Preinscripcion.objects.exists())

    def test_periodo_cerrado(self):
        PeriodoInscripcion.objects.update(fecha_hasta=timezone.now() - timedelta(minutes=1),
                                          fecha_desde=timezone.now() - timedelta(days=2))
        self.assertContains(self.client.get(self.url), "no está abierta")
