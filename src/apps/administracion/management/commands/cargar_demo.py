"""
Carga los datos mínimos para probar el circuito de ingreso.

    docker compose exec web python manage.py cargar_demo

Crea un período abierto, cinco carreras con su plan y cupo, y un usuario
de secretaría. No crea aspirantes: se cargan desde el formulario público.
Se puede correr más de una vez: no duplica lo que ya existe.
"""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.administracion.permisos import GRUPO_ADMINISTRATIVO
from apps.core.models import Carrera, PeriodoInscripcion, PeriodoPlan, PlanCarrera

# (código, nombre, nombre corto, resolución, cupo)
CARRERAS = [
    ("TSADSI", "Tecnicatura Superior en Análisis y Desarrollo de Sistemas Informáticos", "Análisis y Desarrollo de Sistemas", "Res. 3010/19", 30),
    ("TSAP", "Tecnicatura Superior en Administración Pública", "Administración Pública", "Res. 845/21", 25),
    ("TSHST", "Tecnicatura Superior en Higiene y Seguridad en el Trabajo", "Higiene y Seguridad", "Res. 2210/18", 20),
    ("TSER", "Tecnicatura Superior en Energías Renovables", "Energías Renovables", "Res. 1187/22", 20),
    ("TSGT", "Tecnicatura Superior en Guía de Turismo", "Guía de Turismo", "Res. 517/20", 3),  # cupo chico para probar "sin cupo"
]


class Command(BaseCommand):
    help = "Carga un período abierto, las carreras con su cupo y un usuario de secretaría."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="siga1234", help="Contraseña del usuario 'secretaria'.")

    @transaction.atomic
    def handle(self, *args, **opciones):
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

        for codigo, nombre, corto, resolucion, cupo in CARRERAS:
            carrera, _ = Carrera.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "nombre_corto": corto})
            plan, _ = PlanCarrera.objects.get_or_create(
                carrera=carrera, codigo=f"{codigo}-PLAN",
                defaults={"nombre": "Plan vigente", "resolucion": resolucion},
            )
            PeriodoPlan.objects.get_or_create(periodo=periodo, plan=plan, defaults={"cupo_ingresantes": cupo})

        usuario, creado = User.objects.get_or_create(
            username="secretaria", defaults={"first_name": "Marta", "last_name": "Quiroga", "is_staff": True}
        )
        if creado:
            usuario.set_password(opciones["password"])
            usuario.save()
        usuario.groups.add(Group.objects.get(name=GRUPO_ADMINISTRATIVO))

        self.stdout.write(self.style.SUCCESS(
            f"Listo. Período '{periodo.nombre}' abierto. Usuario: secretaria (ver README para la contraseña)."
        ))
