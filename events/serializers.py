from decimal import Decimal

from rest_framework import serializers

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from django.db import transaction

from .models import (
    LIMITE_HORAS_DEFECTO,
    LIMITE_HORAS_MAX,
    LIMITE_HORAS_MIN,
    Evento,
    Gestion,
    PreferenciasUsuario,
)


HORAS_GESTION_MIN = Decimal("0.5")
HORAS_GESTION_MAX = Decimal("8")
CAMPOS_GESTION_OBLIGATORIOS = ("nombre", "fecha", "hora", "horas")


def validar_horas_gestion(value):
    """Horas estimadas de una gestión: entre 0,5 y 8."""
    if value < HORAS_GESTION_MIN or value > HORAS_GESTION_MAX:
        raise serializers.ValidationError(
            "El tiempo estimado debe estar entre 0,5 y 8 horas."
        )
    return value


def _campo_limite_horas(**kwargs):
    """Campo de límite de horas al día (1–12), igual que el formulario."""
    return serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        min_value=LIMITE_HORAS_MIN,
        max_value=LIMITE_HORAS_MAX,
        coerce_to_string=False,  # el frontend lo recibe como número
        error_messages={
            "invalid": "Ingresa un límite de horas válido (por ejemplo: 8 o 8.5).",
            "min_value": f"El límite debe ser de al menos {LIMITE_HORAS_MIN} hora.",
            "max_value": f"El límite no puede superar {LIMITE_HORAS_MAX} horas al día.",
        },
        **kwargs,
    )


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
        return validar_horas_gestion(value)


class GestionEventoSerializer(GestionSerializer):
    """Gestión dentro de un evento. Acepta 'id' para editar una gestión que
    ya existe; sin 'id' se crea una nueva."""

    id = serializers.IntegerField(required=False)


class EventoSerializer(serializers.ModelSerializer):
    gestiones = GestionEventoSerializer(many=True)
    # Opcional: si no llega, se usa el límite guardado en las preferencias del usuario
    limite_horas = _campo_limite_horas(required=False)

    class Meta:
        model = Evento
        fields = ["id", "nombre", "fecha", "limite_horas", "gestiones"]

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
        if self.instance is None:
            # Al crear, el plan necesita al menos una gestión. Al editar, la
            # lista solo trae las gestiones a agregar o modificar.
            if not value:
                raise serializers.ValidationError(
                    "Añade al menos una gestión al plan."
                )
            return value

        propias = set(self.instance.gestiones.values_list("id", flat=True))
        for datos in value:
            gestion_id = datos.get("id")
            if gestion_id is None:
                # Nueva gestión: en PATCH el serializador anidado no exige
                # campos, así que se revisan aquí para no fallar al guardar.
                faltan = [c for c in CAMPOS_GESTION_OBLIGATORIOS if c not in datos]
                if faltan:
                    raise serializers.ValidationError(
                        "Cada gestión nueva necesita: " + ", ".join(faltan) + "."
                    )
            elif gestion_id not in propias:
                raise serializers.ValidationError(
                    f"La gestión {gestion_id} no pertenece a este evento."
                )
        return value

    def create(self, validated_data):
        gestiones_data = validated_data.pop("gestiones")
        if "limite_horas" not in validated_data:
            usuario = validated_data.get("usuario")
            validated_data["limite_horas"] = (
                PreferenciasUsuario.de_usuario(usuario).limite_horas
                if usuario
                else LIMITE_HORAS_DEFECTO
            )
        evento = Evento.objects.create(**validated_data)
        Gestion.objects.bulk_create(
            [
                Gestion(evento=evento, **{k: v for k, v in g.items() if k != "id"})
                for g in gestiones_data
            ]
        )
        return evento

    @transaction.atomic
    def update(self, instance, validated_data):
        """Edita el evento y su plan.

        'gestiones' es opcional: cada elemento con 'id' edita esa gestión y
        cada elemento sin 'id' crea una nueva. Las gestiones que no se
        mencionan quedan como están (borrar sigue siendo
        DELETE /api/gestiones/<id>/).
        """
        gestiones_data = validated_data.pop("gestiones", None)
        instance.nombre = validated_data.get("nombre", instance.nombre)
        instance.fecha = validated_data.get("fecha", instance.fecha)
        instance.limite_horas = validated_data.get("limite_horas", instance.limite_horas)
        instance.save()

        if gestiones_data:
            existentes = {g.id: g for g in instance.gestiones.all()}
            nuevas = []
            for datos in gestiones_data:
                gestion_id = datos.pop("id", None)
                if gestion_id is None:
                    nuevas.append(Gestion(evento=instance, **datos))
                else:
                    gestion = existentes[gestion_id]
                    for campo, valor in datos.items():
                        setattr(gestion, campo, valor)
                    gestion.save()
            Gestion.objects.bulk_create(nuevas)
        return instance
class PreferenciasSerializer(serializers.ModelSerializer):
    limite_horas = _campo_limite_horas()

    class Meta:
        model = PreferenciasUsuario
        fields = ["limite_horas"]

class ReprogramarSerializer(serializers.Serializer):
    """Datos para mover una gestión a otro día."""

    fecha = serializers.DateField(help_text="Día destino (YYYY-MM-DD)")
    hora = serializers.TimeField(
        required=False, help_text="Nueva hora (HH:MM). Si se omite, conserva la actual."
    )
    horas = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        required=False,
        help_text="Nuevas horas estimadas (0,5 a 8). Si se omite, conserva las actuales.",
    )

    def validate_horas(self, value):
        return validar_horas_gestion(value)

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

class ConflictoSobrecargaDetalleSerializer(serializers.Serializer):
    fecha = serializers.DateField(help_text="Día destino que se pasaría del límite.")
    horas = serializers.FloatField(
        help_text="Horas que tendría ese día con la gestión incluida."
    )
    limite = serializers.FloatField(help_text="Límite de horas al día que se aplicó.")
    exceso = serializers.FloatField(help_text="Horas que se pasa: horas - limite.")
    gestiones = GestionHoySerializer(
        many=True,
        help_text="Gestiones que ya cuentan ese día (sin incluir la que se mueve).",
    )


class ConflictoErrorSerializer(serializers.Serializer):
    status = serializers.IntegerField()
    message = serializers.CharField()
    details = ConflictoSobrecargaDetalleSerializer()


class ConflictoRespuestaSerializer(serializers.Serializer):
    success = serializers.BooleanField(default=False)
    error = ConflictoErrorSerializer()
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