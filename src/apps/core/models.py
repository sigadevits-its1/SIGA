"""
Datos que comparte todo el SIGA: personas y oferta académica.

En esta etapa las carreras, planes y períodos se cargan desde el admin
de Django (decisión provisional del primer entregable, sección 3.2).
"""
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

validar_dni = RegexValidator(r"^\d{7,8}$", "El DNI debe tener 7 u 8 números, sin puntos.")


class Persona(models.Model):
    """Una persona física. Hoy son aspirantes; más adelante, estudiantes y docentes."""

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    dni = models.CharField("DNI", max_length=8, unique=True, validators=[validar_dni])
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    email = models.EmailField("correo electrónico", max_length=150)
    telefono = models.CharField("teléfono", max_length=40)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "personas"
        ordering = ["apellido", "nombre"]

    def __str__(self):
        return f"{self.apellido}, {self.nombre} ({self.dni})"

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"

    @property
    def iniciales(self):
        return (self.nombre[:1] + self.apellido[:1]).upper()

    @property
    def edad(self):
        hoy = timezone.localdate()
        nac = self.fecha_nacimiento
        return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))

    @property
    def dni_con_puntos(self):
        return f"{int(self.dni):,}".replace(",", ".")


class Carrera(models.Model):
    codigo = models.CharField("código", max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    nombre_corto = models.CharField("nombre corto", max_length=60, help_text="Se usa en listados.")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "carreras"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class PlanCarrera(models.Model):
    carrera = models.ForeignKey(Carrera, on_delete=models.PROTECT, related_name="planes")
    codigo = models.CharField("código", max_length=30)
    nombre = models.CharField(max_length=150)
    resolucion = models.CharField("resolución", max_length=100, blank=True)
    duracion_anios = models.PositiveSmallIntegerField("duración (años)", default=3)

    class Meta:
        db_table = "planes_carreras"
        verbose_name = "plan de carrera"
        verbose_name_plural = "planes de carrera"
        constraints = [
            models.UniqueConstraint(fields=["carrera", "codigo"], name="plan_codigo_unico_por_carrera"),
        ]

    def __str__(self):
        return f"{self.carrera.nombre_corto} · {self.nombre}"


class PeriodoInscripcionQuerySet(models.QuerySet):
    def abierto(self):
        """El período cuya ventana de fechas incluye el momento actual."""
        ahora = timezone.now()
        return self.filter(fecha_desde__lte=ahora, fecha_hasta__gte=ahora).order_by("-fecha_desde").first()

    def actual(self):
        """El período abierto o, si no hay, el más reciente."""
        return self.abierto() or self.order_by("-fecha_desde").first()


class PeriodoInscripcion(models.Model):
    codigo = models.CharField("código", max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    ciclo_lectivo = models.PositiveSmallIntegerField("ciclo lectivo")
    fecha_desde = models.DateTimeField("desde")
    fecha_hasta = models.DateTimeField("hasta")

    objects = PeriodoInscripcionQuerySet.as_manager()

    class Meta:
        db_table = "periodos_inscripcion"
        verbose_name = "período de inscripción"
        verbose_name_plural = "períodos de inscripción"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_hasta__gt=models.F("fecha_desde")),
                name="periodo_fechas_validas",
            ),
        ]

    def __str__(self):
        return self.nombre

    def esta_abierto(self):
        return self.fecha_desde <= timezone.now() <= self.fecha_hasta


class PeriodoPlan(models.Model):
    """Un plan que se ofrece en un período, con su cupo. Es lo que elige el aspirante."""

    periodo = models.ForeignKey(PeriodoInscripcion, on_delete=models.PROTECT, related_name="planes")
    plan = models.ForeignKey(PlanCarrera, on_delete=models.PROTECT, related_name="periodos")
    cupo_ingresantes = models.PositiveIntegerField(
        "cupo de ingresantes", null=True, blank=True, help_text="Vacío = sin límite."
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "periodos_inscripcion_planes"
        verbose_name = "plan ofrecido en el período"
        verbose_name_plural = "planes ofrecidos en el período"
        constraints = [
            models.UniqueConstraint(fields=["periodo", "plan"], name="plan_unico_por_periodo"),
        ]

    def __str__(self):
        return f"{self.periodo} · {self.plan}"

    @property
    def carrera(self):
        return self.plan.carrera
