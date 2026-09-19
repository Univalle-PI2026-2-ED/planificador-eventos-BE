from rest_framework import serializers

from .models import Evento, Gestion


class GestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gestion
        fields = ["id", "nombre", "fecha", "hora", "horas", "estado", "nota"]

    def validate_nombre(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Cada gestión necesita un nombre."
            )
        return value.strip()

    def validate_horas(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "El tiempo estimado debe ser un número mayor a 0."
            )
        return value


class EventoSerializer(serializers.ModelSerializer):
    gestiones = GestionSerializer(many=True)

    class Meta:
        model = Evento
        fields = ["id", "nombre", "fecha", "gestiones"]

    def validate_nombre(self, value):
        nombre = value.strip()
        if not nombre:
            raise serializers.ValidationError(
                "Escribe un nombre para reconocer el evento."
            )
        qs = Evento.objects.filter(nombre__iexact=nombre)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe un evento con ese nombre. Usa uno distinto para diferenciarlos."
            )
        return nombre

    def validate_gestiones(self, value):
        if not value:
            raise serializers.ValidationError(
                "Añade al menos una gestión al plan."
            )
        return value

    def create(self, validated_data):
        gestiones_data = validated_data.pop("gestiones")
        evento = Evento.objects.create(**validated_data)
        Gestion.objects.bulk_create(
            [Gestion(evento=evento, **g) for g in gestiones_data]
        )
        return evento

    def update(self, instance, validated_data):
        # Las gestiones se crean/editan/borran por su propio endpoint
        # (/api/gestiones/<id>/), no reemplazando la lista completa aquí.
        validated_data.pop("gestiones", None)
        instance.nombre = validated_data.get("nombre", instance.nombre)
        instance.fecha = validated_data.get("fecha", instance.fecha)
        instance.save()
        return instance