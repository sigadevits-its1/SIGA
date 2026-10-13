from django import forms
from django.db import transaction

from apps.admisiones.cupos import tiene_cupo
from apps.admisiones.models import DocumentoPreinscripcion, Preinscripcion
from apps.admisiones.validadores import validar_extension, validar_tamanio
from apps.core.models import PeriodoPlan, Persona, validar_dni

Tipo = DocumentoPreinscripcion.Tipo
VALIDADORES_ARCHIVO = [validar_extension, validar_tamanio]
ACEPTA_ARCHIVOS = {"accept": ".pdf,.jpg,.jpeg,.png"}


def caja(tipo=forms.TextInput, **attrs):
    """Widget con la clase visual "control" del diseño SIGA."""
    return tipo(attrs={"class": "control", **attrs})


class PreinscripcionForm(forms.Form):
    # --- Paso 1: datos personales y de contacto ---
    nombre = forms.CharField(max_length=100, widget=caja(autocomplete="given-name"))
    apellido = forms.CharField(max_length=100, widget=caja(autocomplete="family-name"))
    dni = forms.CharField(label="DNI", max_length=8, validators=[validar_dni], widget=caja(inputmode="numeric"))
    # Calendario flatpickr (formulario.js). Se envía como AAAA-MM-DD; se muestra como DD/MM/AAAA.
    fecha_nacimiento = forms.DateField(
        widget=forms.DateInput(
            format="%Y-%m-%d", attrs={"class": "control", "placeholder": "dd/mm/aaaa", "data-calendario": ""}
        )
    )
    email = forms.EmailField(max_length=150, widget=caja(forms.EmailInput, autocomplete="email"))
    email_confirmacion = forms.EmailField(widget=caja(forms.EmailInput, autocomplete="off"))
    telefono = forms.CharField(max_length=40, widget=caja(forms.TextInput, type="tel", autocomplete="tel"))

    # --- Paso 2: carrera (las opciones dependen del período) ---
    oferta = forms.ModelChoiceField(
        queryset=PeriodoPlan.objects.none(),
        error_messages={"required": "Elegí la carrera a la que querés inscribirte."},
    )

    # --- Paso 3: documentación ---
    archivo_dni = forms.FileField(validators=VALIDADORES_ARCHIVO, widget=forms.FileInput(ACEPTA_ARCHIVOS))
    # Título secundario o constancia de título en trámite: uno u otro.
    titulo_situacion = forms.ChoiceField(
        choices=[(Tipo.TITULO, "Tengo el título"), (Tipo.TITULO_EN_TRAMITE, "Está en trámite")],
        initial=Tipo.TITULO,
        widget=forms.RadioSelect,
    )
    archivo_titulo = forms.FileField(validators=VALIDADORES_ARCHIVO, widget=forms.FileInput(ACEPTA_ARCHIVOS))
    archivo_analitico = forms.FileField(
        required=False, validators=VALIDADORES_ARCHIVO, widget=forms.FileInput(ACEPTA_ARCHIVOS)
    )

    # --- Paso 4: declaración y envío ---
    declaracion = forms.BooleanField()
    privacidad = forms.BooleanField()
    # Campo trampa: es invisible, así que sólo un robot lo completa.
    website = forms.CharField(required=False)

    def __init__(self, *args, periodo, **kwargs):
        super().__init__(*args, **kwargs)
        self.periodo = periodo
        self.fields["oferta"].queryset = PeriodoPlan.objects.filter(periodo=periodo, activo=True)

    def clean_dni(self):
        dni = self.cleaned_data["dni"]
        ya_tiene = Preinscripcion.objects.filter(
            persona__dni=dni,
            periodo_plan__periodo=self.periodo,
            estado__in=[Preinscripcion.Estado.PENDIENTE, Preinscripcion.Estado.ACEPTADO],
        ).exists()
        if ya_tiene:
            raise forms.ValidationError(
                "Ya hay una solicitud con este DNI en el período. Si tenés dudas, consultá en secretaría."
            )
        return dni

    def clean_oferta(self):
        oferta = self.cleaned_data["oferta"]
        if not tiene_cupo(oferta):
            raise forms.ValidationError("Esta carrera no tiene cupo disponible.")
        return oferta

    def clean(self):
        datos = super().clean()
        email, confirmacion = datos.get("email"), datos.get("email_confirmacion")
        if email and confirmacion and email.lower() != confirmacion.lower():
            self.add_error("email_confirmacion", "Los correos no coinciden.")
        if datos.get("website"):
            raise forms.ValidationError("No pudimos procesar el envío.")
        return datos

    @transaction.atomic
    def save(self):
        """Guarda la persona, la solicitud y sus documentos en una sola transacción."""
        d = self.cleaned_data
        persona, _ = Persona.objects.update_or_create(
            dni=d["dni"],
            defaults={
                "nombre": d["nombre"].strip(),
                "apellido": d["apellido"].strip(),
                "fecha_nacimiento": d["fecha_nacimiento"],
                "email": d["email"].lower(),
                "telefono": d["telefono"].strip(),
            },
        )
        preinscripcion = Preinscripcion.objects.create(persona=persona, periodo_plan=d["oferta"])

        archivos = {
            Tipo.DNI: d["archivo_dni"],
            d["titulo_situacion"]: d["archivo_titulo"],
            Tipo.ANALITICO: d.get("archivo_analitico"),
        }
        for tipo, archivo in archivos.items():
            if archivo:
                DocumentoPreinscripcion.objects.create(
                    preinscripcion=preinscripcion, tipo=tipo, archivo=archivo, nombre_original=archivo.name
                )
        return preinscripcion
