from django.contrib import admin

from .models import DocumentoPreinscripcion, Preinscripcion


class DocumentoInline(admin.TabularInline):
    model = DocumentoPreinscripcion
    extra = 0


@admin.register(Preinscripcion)
class PreinscripcionAdmin(admin.ModelAdmin):
    list_display = ["id", "persona", "periodo_plan", "estado", "fecha_preinscripcion", "revisor"]
    list_filter = ["estado", "periodo_plan__periodo", "periodo_plan__plan__carrera"]
    search_fields = ["persona__apellido", "persona__nombre", "persona__dni"]
    inlines = [DocumentoInline]
