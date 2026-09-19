from django.contrib import admin

from .models import Evento, Gestion


class GestionInline(admin.TabularInline):
    model = Gestion
    extra = 0


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha", "creado_en")
    search_fields = ("nombre",)
    inlines = [GestionInline]


@admin.register(Gestion)
class GestionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "evento", "fecha", "hora", "horas", "estado")
    list_filter = ("estado", "fecha")
    search_fields = ("nombre",)