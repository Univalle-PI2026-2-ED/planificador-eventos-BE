from rest_framework import serializers

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
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
        user = self.context["request"].user
        qs = Evento.objects.filter(usuario=user, nombre__iexact=nombre)
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



class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
        }

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Escribe un nombre de usuario.")
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con ese correo."
            )
        return email

    def validate(self, attrs):
        # Se valida la contraseña con las reglas de AUTH_PASSWORD_VALIDATORS
        # (largo mínimo, muy común, solo números, parecida al usuario).
        user = User(username=attrs.get("username"), email=attrs.get("email"))
        try:
            password_validation.validate_password(attrs["password"], user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        username = attrs.get("username", "").strip()
        email = attrs.get("email", "").strip().lower()

        if not username and not email:
            raise serializers.ValidationError("Escribe tu usuario o tu correo.")

        # Si entra con correo, se busca el usuario dueño de ese correo
        if not username:
            usuario = User.objects.filter(email__iexact=email).first()
            username = usuario.username if usuario else None

        user = None
        if username:
            user = authenticate(
                request=self.context.get("request"),
                username=username,
                password=attrs["password"],
            )
        if user is None:
            raise serializers.ValidationError(
                "Usuario o contraseña incorrectos."
            )
        attrs["user"] = user
        return attrs

class EventoResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evento
        fields = ["id", "nombre"]


class GestionHoySerializer(serializers.ModelSerializer):
    """Gestión con el evento embebido, como lo usa Hoy.jsx (g.evento.id / g.evento.nombre)."""
    evento = EventoResumenSerializer(read_only=True)

    class Meta:
        model = Gestion
        fields = ["id", "nombre", "fecha", "hora", "horas", "estado", "nota", "evento"]
    



##ESTO ES SOLO PARA DOCUMENTAR 
class UsuarioSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()


class AuthRespuestaSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text="Úsalo en el header: Authorization: Token <token>"
    )
    user = UsuarioSerializer()


class ErrorDetalleSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    message = serializers.CharField()
    details = serializers.DictField(
        help_text="Errores por campo, o 'detail' en errores generales."
    )


class ErrorRespuestaSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)
    error = ErrorDetalleSerializer()


class HoyGruposSerializer(serializers.Serializer):
    vencidas = GestionHoySerializer(many=True)
    para_hoy = GestionHoySerializer(many=True)
    proximas = GestionHoySerializer(many=True)


class HoyResumenSerializer(serializers.Serializer):
    vencidas = serializers.IntegerField()
    para_hoy = serializers.IntegerField()
    proximas = serializers.IntegerField()


class HoyFiltrosSerializer(serializers.Serializer):
    estado = serializers.CharField()
    orden = serializers.CharField()
    dias = serializers.IntegerField(allow_null=True)


class HoyRespuestaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    hora = serializers.CharField(help_text="HH:MM, hora local usada para clasificar.")
    filtros = HoyFiltrosSerializer()
    resumen = HoyResumenSerializer()
    grupos = HoyGruposSerializer()