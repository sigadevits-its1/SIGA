from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

EXTENSIONES_PERMITIDAS = ["pdf", "jpg", "jpeg", "png"]

validar_extension = FileExtensionValidator(
    allowed_extensions=EXTENSIONES_PERMITIDAS,
    message="Formato no válido. Usá PDF, JPG o PNG.",
)


def validar_tamanio(archivo):
    maximo = settings.MAX_TAMANIO_DOCUMENTO
    if archivo.size > maximo:
        raise ValidationError(
            f"El archivo pesa {archivo.size / 1048576:.1f} MB. El máximo es {maximo // 1048576} MB."
        )
