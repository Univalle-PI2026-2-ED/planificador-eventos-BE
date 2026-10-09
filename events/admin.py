from django.contrib import admin

from .models import Evento, Gestion, PreferenciasUsuario


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


@admin.register(PreferenciasUsuario)
class PreferenciasUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "limite_horas", "actualizado_en")
    search_fields = ("usuario__username",)