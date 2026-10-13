from django.contrib import admin

from .models import Carrera, PeriodoInscripcion, PeriodoPlan, Persona, PlanCarrera


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ["apellido", "nombre", "dni", "email", "telefono"]
    search_fields = ["apellido", "nombre", "dni", "email"]


class PlanCarreraInline(admin.TabularInline):
    model = PlanCarrera
    extra = 0


@admin.register(Carrera)
class CarreraAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo", "nombre_corto", "activo"]
    inlines = [PlanCarreraInline]


class PeriodoPlanInline(admin.TabularInline):
    model = PeriodoPlan
    extra = 0


@admin.register(PeriodoInscripcion)
class PeriodoInscripcionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "codigo", "ciclo_lectivo", "fecha_desde", "fecha_hasta"]
    inlines = [PeriodoPlanInline]
