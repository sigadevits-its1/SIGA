"""
Envía un correo de prueba para verificar la configuración.

    docker compose exec web python manage.py probar_correo tu@correo.com
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envía un correo de prueba a la dirección indicada."

    def add_arguments(self, parser):
        parser.add_argument("destinatario")

    def handle(self, *args, destinatario, **opciones):
        if "console" in settings.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING(
                "Modo consola: el correo NO se envía, se imprime abajo. "
                "Para enviarlo por Gmail, completá EMAIL_HOST_PASSWORD en .env y reiniciá: docker compose up -d"
            ))
        else:
            self.stdout.write(f"Enviando por {settings.EMAIL_HOST} como {settings.EMAIL_HOST_USER}...")

        try:
            send_mail(
                subject="SIGA · Correo de prueba",
                message="Si recibiste este mensaje, el envío de correos de SIGA funciona.",
                from_email=None,
                recipient_list=[destinatario],
            )
        except Exception as error:
            raise CommandError(f"No se pudo enviar: {error}")

        self.stdout.write(self.style.SUCCESS("Listo."))
