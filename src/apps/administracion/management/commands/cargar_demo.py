"""
Carga datos de ejemplo para probar el circuito de ingreso.

    docker compose exec web python manage.py cargar_demo

Crea un período abierto, cinco carreras con su plan y cupo, un usuario de
secretaría y algunos aspirantes con documentación. Se puede correr más de
una vez: no duplica lo que ya existe.
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.administracion.permisos import GRUPO_ADMINISTRATIVO
from apps.admisiones.models import DocumentoPreinscripcion, Preinscripcion
from apps.core.models import Carrera, PeriodoInscripcion, PeriodoPlan, Persona, PlanCarrera

# (código, nombre, nombre corto, resolución, cupo)
CARRERAS = [
    ("TSADSI", "Tecnicatura Superior en Análisis y Desarrollo de Sistemas Informáticos", "Análisis y Desarrollo de Sistemas", "Res. 3010/19", 30),
    ("TSAP", "Tecnicatura Superior en Administración Pública", "Administración Pública", "Res. 845/21", 25),
    ("TSHST", "Tecnicatura Superior en Higiene y Seguridad en el Trabajo", "Higiene y Seguridad", "Res. 2210/18", 20),
    ("TSER", "Tecnicatura Superior en Energías Renovables", "Energías Renovables", "Res. 1187/22", 20),
    ("TSGT", "Tecnicatura Superior en Guía de Turismo", "Guía de Turismo", "Res. 517/20", 3),  # cupo chico: se llena con los aspirantes de ejemplo
]

ASPIRANTES = [
    ("Sofía", "Martínez", "TSADSI"), ("Mateo", "López", "TSADSI"), ("Valentina", "Ríos", "TSAP"),
    ("Joaquín", "Fernández", "TSADSI"), ("Camila", "Acosta", "TSHST"), ("Nicolás", "Benítez", "TSER"),
    ("Lucía", "Catriel", "TSGT"), ("Thiago", "Sosa", "TSGT"), ("Martina", "Huenchul", "TSGT"),
    ("Benjamín", "Gómez", "TSAP"), ("Agustina", "Díaz", "TSADSI"), ("Tomás", "Painemal", "TSER"),
    ("Florencia", "Romero", "TSHST"), ("Santiago", "Torres", "TSADSI"), ("Milagros", "Quiroga", "TSAP"),
]


def pdf_de_ejemplo(texto):
    """Genera un PDF mínimo de una página con un texto, sin librerías externas."""
    contenido = f"BT /F1 18 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(contenido) + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = b"%PDF-1.4\n"
    posiciones = []
    for i, obj in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)
    return salida


class Command(BaseCommand):
    help = "Carga un período, carreras, un usuario de secretaría y aspirantes de ejemplo."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="siga1234", help="Contraseña del usuario 'secretaria'.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        rnd = random.Random(2027)
        ahora = timezone.now()
        ciclo = ahora.year + 1

        periodo, _ = PeriodoInscripcion.objects.get_or_create(
            codigo=f"ING-{ciclo}",
            defaults={
                "nombre": f"Ingreso {ciclo}",
                "ciclo_lectivo": ciclo,
                "fecha_desde": ahora - timedelta(days=30),
                "fecha_hasta": ahora + timedelta(days=60),
            },
        )

        ofertas = {}
        for codigo, nombre, corto, resolucion, cupo in CARRERAS:
            carrera, _ = Carrera.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "nombre_corto": corto})
            plan, _ = PlanCarrera.objects.get_or_create(
                carrera=carrera, codigo=f"{codigo}-PLAN",
                defaults={"nombre": "Plan vigente", "resolucion": resolucion},
            )
            ofertas[codigo], _ = PeriodoPlan.objects.get_or_create(
                periodo=periodo, plan=plan, defaults={"cupo_ingresantes": cupo}
            )

        grupo = Group.objects.get(name=GRUPO_ADMINISTRATIVO)
        usuario, creado = User.objects.get_or_create(
            username="secretaria", defaults={"first_name": "Marta", "last_name": "Quiroga", "is_staff": True}
        )
        if creado:
            usuario.set_password(opciones["password"])
            usuario.save()
        usuario.groups.add(grupo)

        if Preinscripcion.objects.filter(periodo_plan__periodo=periodo).exists():
            self.stdout.write("Ya había aspirantes de ejemplo; no se agregan más.")
        else:
            for nombre, apellido, codigo in ASPIRANTES:
                self.crear_aspirante(rnd, nombre, apellido, ofertas[codigo])
            self.stdout.write(f"Se crearon {len(ASPIRANTES)} aspirantes de ejemplo.")

        self.stdout.write(self.style.SUCCESS(
            f"Listo. Período '{periodo.nombre}' abierto. Usuario: secretaria (ver README para la contraseña)."
        ))

    def crear_aspirante(self, rnd, nombre, apellido, oferta):
        sin_tildes = nombre.translate(str.maketrans("áéíóúñ", "aeioun")).lower()
        persona = Persona.objects.create(
            nombre=nombre,
            apellido=apellido,
            dni=str(45000000 + rnd.randint(0, 2999999)),
            fecha_nacimiento=date(2000 + rnd.randint(0, 7), rnd.randint(1, 12), rnd.randint(1, 28)),
            email=f"{sin_tildes}.{apellido.lower()}@example.com".translate(str.maketrans("áéíóúñ", "aeioun")),
            telefono=f"+54 9 2920 4{rnd.randint(10000, 99999)}",
        )
        p = Preinscripcion.objects.create(persona=persona, periodo_plan=oferta)

        tipos = [DocumentoPreinscripcion.Tipo.DNI, rnd.choice(["titulo", "titulo_en_tramite"])]
        if rnd.random() < 0.6:
            tipos.append(DocumentoPreinscripcion.Tipo.ANALITICO)
        for tipo in tipos:
            etiqueta = DocumentoPreinscripcion.Tipo(tipo).label
            nombre_archivo = f"{tipo}_{apellido}{nombre}.pdf"
            doc = DocumentoPreinscripcion(preinscripcion=p, tipo=tipo, nombre_original=nombre_archivo)
            doc.archivo.save(nombre_archivo, ContentFile(pdf_de_ejemplo(f"{etiqueta} - {nombre} {apellido}")), save=True)
        # Todas quedan pendientes: secretaría las acepta o rechaza desde el panel.
