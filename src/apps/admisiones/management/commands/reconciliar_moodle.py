"""Revincula cuentas de Moodle en solicitudes aceptadas sin ID vinculado.

Es un reparador manual: no crea ni modifica cuentas en Moodle, sólo busca
por DNI las que ya existen y guarda su ID en la persona.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.admisiones.models import Preinscripcion
from apps.admisiones.moodle import MoodleIntegrationError, buscar_usuario_moodle


class Command(BaseCommand):
    help = "Reconcilia solicitudes aceptadas cuyo usuario de Moodle no quedó vinculado."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **opciones):
        pendientes = Preinscripcion.objects.filter(
            estado=Preinscripcion.Estado.ACEPTADO,
            persona__moodle_user_id__isnull=True,
        ).select_related("persona")

        for p in pendientes:
            self.stdout.write(f"Revisando {p.numero} ({p.persona.dni})...")
            try:
                moodle_id = buscar_usuario_moodle(p.persona.dni)
            except MoodleIntegrationError as error:
                self.stderr.write(f"  Error: {error}")
                continue

            if moodle_id is None:
                self.stdout.write("  No existe en Moodle. Se puede reintentar la creación.")
                continue

            self.stdout.write(f"  Existe en Moodle con ID {moodle_id}.")
            # Vincular la cuenta existente y limpiar el error anterior.
            if not dry_run:
                p.persona.moodle_user_id = moodle_id
                p.persona.save(update_fields=["moodle_user_id", "actualizado"])
                p.moodle_estado = Preinscripcion.MoodleEstado.CREADO
                p.moodle_error = ""
                p.moodle_actualizado = timezone.now()
                p.save(update_fields=["moodle_estado", "moodle_error", "moodle_actualizado"])