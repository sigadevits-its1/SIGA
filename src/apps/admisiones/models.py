"""
Preinscripciones y su documentación.

Regla de esta etapa: la solicitud es "todo o nada". Queda pendiente hasta
que secretaría la acepta o la rechaza. Si se rechaza, el aspirante recibe
un correo y vuelve a completar el formulario desde cero.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import PeriodoPlan, Persona

from .validadores import validar_extension, validar_tamanio


class Preinscripcion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ACEPTADO = "aceptado", "Aceptado"
        RECHAZADO = "rechazado", "Rechazado"

    persona = models.ForeignKey(Persona, on_delete=models.PROTECT, related_name="preinscripciones")
    periodo_plan = models.ForeignKey(
        PeriodoPlan, on_delete=models.PROTECT, related_name="preinscripciones", verbose_name="carrera y plan"
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    observaciones = models.TextField(blank=True)
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    fecha_revision = models.DateTimeField("fecha de resolución", null=True, blank=True)
    fecha_preinscripcion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "preinscripciones"
        verbose_name = "preinscripción"
        verbose_name_plural = "preinscripciones"
        ordering = ["-fecha_preinscripcion"]
        constraints = [
            # Una persona no puede tener dos solicitudes vivas para la misma carrera.
            # Las rechazadas no cuentan: así puede volver a enviar el formulario.
            models.UniqueConstraint(
                fields=["persona", "periodo_plan"],
                condition=~models.Q(estado="rechazado"),
                name="una_preinscripcion_activa_por_plan",
            ),
        ]

    def __str__(self):
        return f"{self.numero} · {self.persona.nombre_completo}"

    @property
    def numero(self):
        """Número de solicitud que se le informa al aspirante, por ejemplo PRE-2027-00012."""
        return f"PRE-{self.periodo_plan.periodo.ciclo_lectivo}-{self.pk:05d}"

    @property
    def esta_pendiente(self):
        return self.estado == self.Estado.PENDIENTE

    def aceptar(self, usuario, observaciones=""):
        self._resolver(self.Estado.ACEPTADO, usuario, observaciones)

    def rechazar(self, usuario, motivo):
        if not motivo.strip():
            raise ValueError("Para rechazar hay que indicar el motivo.")
        self._resolver(self.Estado.RECHAZADO, usuario, motivo)

    def _resolver(self, estado, usuario, observaciones):
        if not self.esta_pendiente:
            raise ValueError("La solicitud ya fue resuelta.")
        self.estado = estado
        self.observaciones = observaciones.strip()
        self.revisor = usuario
        self.fecha_revision = timezone.now()
        self.save()


def ruta_documento(documento, nombre_original):
    """Guarda cada archivo con un nombre aleatorio, para que la ruta no se pueda adivinar."""
    extension = Path(nombre_original).suffix.lower()
    return f"preinscripciones/{uuid.uuid4().hex}{extension}"


class DocumentoPreinscripcion(models.Model):
    class Tipo(models.TextChoices):
        DNI = "dni", "Documento de identidad"
        TITULO = "titulo", "Título secundario"
        TITULO_EN_TRAMITE = "titulo_en_tramite", "Constancia de título en trámite"
        ANALITICO = "analitico", "Certificado analítico"

    preinscripcion = models.ForeignKey(Preinscripcion, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    archivo = models.FileField(upload_to=ruta_documento, validators=[validar_extension, validar_tamanio])
    nombre_original = models.CharField(max_length=255)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documentos_preinscripciones"
        verbose_name = "documento"
        ordering = ["creado"]
        constraints = [
            models.UniqueConstraint(fields=["preinscripcion", "tipo"], name="un_documento_por_tipo"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.nombre_original}"

    @property
    def extension(self):
        return Path(self.nombre_original).suffix.lstrip(".").upper()
