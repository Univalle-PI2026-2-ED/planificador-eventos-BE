from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from .exceptions import ConflictoSobrecarga
from .models import Evento, Gestion, PreferenciasUsuario

from .serializers import (
    AuthRespuestaSerializer,
    ConflictoRespuestaSerializer,
    ErrorRespuestaSerializer,
    EventoSerializer,
    GestionHoySerializer,
    GestionSerializer,
    HoyRespuestaSerializer,
    LoginSerializer,
    PreferenciasSerializer,
    RegistroSerializer,
    ReprogramarSerializer,
)
@extend_schema(
    tags=["health"],
    summary="Estado de la API",
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API del Planificador de Eventos funcionando"
    })


class EventoViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/eventos/
    GET/PATCH/PUT/DELETE /api/eventos/<id>/
    POST /api/eventos/<id>/subtareas/

    Cada usuario solo ve y modifica sus propios eventos.

    **Editar el plan:** en PATCH/PUT, `gestiones` es opcional. Cada elemento
    con `id` edita esa gestión del evento; cada elemento sin `id` crea una
    gestión nueva (nombre, fecha, hora y horas son obligatorios). Las
    gestiones que no se mencionan no se tocan; para borrar una se usa
    DELETE /api/gestiones/<id>/.
    """
    serializer_class = EventoSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            # drf-spectacular genera el schema sin usuario real
            return Evento.objects.none()
        return Evento.objects.filter(
            usuario=self.request.user
        ).prefetch_related("gestiones")

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    @action(detail=True, methods=["post"], url_path="subtareas")
    def subtareas(self, request, pk=None):
        """Agrega una gestión (subtarea logística) a un evento que ya existe.

        Cubre US-02 Escenario 1: 'Dado que existe un evento, cuando agrego
        una subtarea logística con datos válidos, entonces el sistema
        guarda la subtarea logística asociada al evento'.
        """
        evento = self.get_object()  # ya viene filtrado por usuario
        serializer = GestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(evento=evento)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
class GestionViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/gestiones/
    GET/PATCH/PUT/DELETE /api/gestiones/<id>/
    POST /api/gestiones/<id>/reprogramar/

    Editar, marcar y guardar nota son PATCH sobre una gestión existente
    (el PATCH no revisa el límite de horas). Para mover una gestión de día
    cuidando el límite, usar POST /api/gestiones/<id>/reprogramar/.
    """
    serializer_class = GestionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Gestion.objects.none()
        return Gestion.objects.filter(
            evento__usuario=self.request.user
        ).select_related("evento")

    def perform_create(self, serializer):
        evento_id = self.request.data.get("evento")
        if not evento_id:
            raise ValidationError({
                "evento": [
                    "Este campo es obligatorio. Indica el id del evento, "
                    "o usa POST /api/eventos/<id>/subtareas/ en su lugar."
                ]
            })
        evento = get_object_or_404(
            Evento, pk=evento_id, usuario=self.request.user
        )
        serializer.save(evento=evento)

    @extend_schema(
        tags=["gestiones"],
        summary="Reprogramar una gestión cuidando el límite diario",
        description=(
            "Mueve la gestión al día `fecha` (y opcionalmente cambia `hora` y "
            "`horas`) y la deja en estado **pendiente**.\n\n"
            "Antes de mover, suma las horas de las gestiones del usuario que "
            "ya están ese día (sin contar las `hecho` ni la gestión que se "
            "mueve) más las horas de esta gestión. Si el total pasa el límite diario configurado "
            "por el usuario (`PreferenciasUsuario.limite_horas`) responde **409** con `fecha`, `horas` "
            "(total del día con esta gestión), `limite`, `exceso` y "
            "`gestiones` (las que ya cuentan ese día) dentro de "
            "`error.details`, y no guarda nada.\n\n"
            "Para mover igual aunque se pase del límite, el frontend usa el "
            "PATCH genérico `/api/gestiones/<id>/`, que no valida el límite."
        ),
        request=ReprogramarSerializer,
        responses={
            200: GestionSerializer,
            400: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Fecha faltante o inválida, u horas fuera de 0,5–8.",
            ),
            401: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Falta el token de autenticación.",
            ),
            404: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="La gestión no existe o no es del usuario.",
            ),
            409: OpenApiResponse(
                response=ConflictoRespuestaSerializer,
                description="El día destino superaría el límite de horas.",
                examples=[
                    OpenApiExample(
                        "Día sobrecargado",
                        value={
                            "success": False,
                            "error": {
                                "status": 409,
                                "message": "Ese día superaría tu límite de horas diario.",
                                "details": {
                                    "fecha": "2026-10-12",
                                    "horas": 7.5,
                                    "limite": 6.0,
                                    "exceso": 1.5,
                                    "gestiones": [
                                        {
                                            "id": 14,
                                            "nombre": "Confirmar catering",
                                            "fecha": "2026-10-12",
                                            "hora": "09:00:00",
                                            "horas": "4.00",
                                            "estado": "pendiente",
                                            "nota": "",
                                            "evento": {"id": 3, "nombre": "Boda de Ana y Luis"},
                                        }
                                    ],
                                },
                            },
                        },
                    )
                ],
            ),
        },
    )
    @action(detail=True, methods=["post"], url_path="reprogramar")
    def reprogramar(self, request, pk=None):
        gestion = self.get_object()  # ya viene filtrado por usuario
        entrada = ReprogramarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        fecha = datos["fecha"]
        horas = datos.get("horas", gestion.horas)
        limite = PreferenciasUsuario.de_usuario(request.user).limite_horas

        with transaction.atomic():
            del_dia = list(
                Gestion.objects.filter(evento__usuario=request.user, fecha=fecha)
                .exclude(estado=Gestion.Estado.HECHO)
                .exclude(pk=gestion.pk)
                .select_related("evento")
                .order_by("hora")
            )
            ya_planeado = sum((g.horas for g in del_dia), Decimal("0"))
            total = ya_planeado + horas

            if total > limite:
                raise ConflictoSobrecarga({
                    "fecha": fecha.isoformat(),
                    "horas": float(total),
                    "limite": float(limite),
                    "exceso": float(total - limite),
                    "gestiones": GestionHoySerializer(del_dia, many=True).data,
                })

            gestion.fecha = fecha
            gestion.horas = horas
            if "hora" in datos:
                gestion.hora = datos["hora"]
            gestion.estado = Gestion.Estado.PENDIENTE
            gestion.save()

        return Response(GestionSerializer(gestion).data)

class RegistroView(generics.GenericAPIView):
    """POST /api/auth/registro/

    Crea un usuario y devuelve su token para que quede con sesión iniciada.
    """
    serializer_class = RegistroSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # un token viejo en el header no debe estorbar


    @extend_schema(
        tags=["auth"],
        summary="Registrar usuario",
        description=(
            "Crea una cuenta y devuelve su token, así el usuario queda con "
            "la sesión iniciada. La contraseña se valida con las reglas de Django "
            "(mínimo 8 caracteres, no demasiado común, no solo números)."
        ),
        request=RegistroSerializer,
        responses={
            201: AuthRespuestaSerializer,
            400: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Usuario o correo repetido, contraseña débil o campos faltantes.",
            ),
        },
    )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(generics.GenericAPIView):
    """POST /api/auth/login/

    Valida las credenciales y devuelve el token del usuario.
    """
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["auth"],
        summary="Iniciar sesión",
        description=(
            "Valida las credenciales y devuelve el token del usuario. Si son "
            "incorrectas, el mensaje llega en error.details.non_field_errors."
        ),
        request=LoginSerializer,
        responses={
            200: AuthRespuestaSerializer,
            400: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Credenciales incorrectas o campos faltantes.",
            ),
        },
    )

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
            status=status.HTTP_200_OK,
        )

class HoyView(generics.GenericAPIView):
    """GET /api/hoy/

    Gestiones del usuario agrupadas en vencidas, para hoy y próximas.
    Misma regla que clasificar() del frontend: una gestión de hoy está
    vencida solo si su hora ya pasó (comparando a nivel de minuto).

    Filtros opcionales (query params):
      estado = pendiente (defecto) | hecho | pospuesto | todas
      orden  = hora (defecto) | esfuerzo (más horas estimadas primero)
      dias   = entero >= 1, limita las próximas a los siguientes N días
    """
    serializer_class = GestionHoySerializer

    ESTADOS = ("pendiente", "hecho", "pospuesto", "todas")
    ORDENES = ("hora", "esfuerzo")

    def _leer_filtros(self, request):
        estado = request.query_params.get("estado", "pendiente")
        orden = request.query_params.get("orden", "hora")
        dias_param = request.query_params.get("dias")

        errores = {}
        if estado not in self.ESTADOS:
            errores["estado"] = [
                "Valor no válido. Usa: pendiente, hecho, pospuesto o todas."
            ]
        if orden not in self.ORDENES:
            errores["orden"] = ["Valor no válido. Usa: hora o esfuerzo."]

        dias = None
        if dias_param is not None:
            try:
                dias = int(dias_param)
                if dias < 1:
                    raise ValueError
            except ValueError:
                errores["dias"] = ["Debe ser un número entero mayor o igual a 1."]

        if errores:
            raise ValidationError(errores)
        return estado, orden, dias

    @extend_schema(
        tags=["hoy"],
        summary="Gestiones del usuario agrupadas por urgencia",
        description=(
            "Devuelve las gestiones de los eventos del usuario autenticado en "
            "tres grupos: **vencidas** (días anteriores, o de hoy con la hora ya "
            "pasada), **para_hoy** (hoy, hora aún por llegar) y **proximas** "
            "(fechas futuras). Los grupos se arman por posición en el tiempo, "
            "sin importar el estado filtrado."
        ),
        parameters=[
            OpenApiParameter(
                "estado", str, enum=["pendiente", "hecho", "pospuesto", "todas"],
                default="pendiente", description="Estado de las gestiones a incluir.",
            ),
            OpenApiParameter(
                "orden", str, enum=["hora", "esfuerzo"], default="hora",
                description="'hora': por fecha y hora. 'esfuerzo': más horas estimadas primero.",
            ),
            OpenApiParameter(
                "dias", int, required=False,
                description="Entero >= 1. Limita las próximas a los siguientes N días.",
            ),
        ],
        responses={
            200: HoyRespuestaSerializer,
            400: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Filtro con valor no válido.",
            ),
            401: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Falta el token de autenticación.",
            ),
        },
    )

    def get(self, request):
        estado, orden, dias = self._leer_filtros(request)

        ahora = timezone.localtime()
        hoy = ahora.date()
        hora_actual = ahora.time().replace(second=0, microsecond=0)

        base = Gestion.objects.select_related("evento").filter(
            evento__usuario=request.user
        )
        if estado != "todas":
            base = base.filter(estado=estado)

        def ordenar(qs):
            if orden == "esfuerzo":
                return qs.order_by("-horas", "fecha", "hora")
            return qs.order_by("fecha", "hora")

        vencidas = ordenar(base.filter(
            Q(fecha__lt=hoy) | Q(fecha=hoy, hora__lt=hora_actual)
        ))
        para_hoy = ordenar(base.filter(fecha=hoy, hora__gte=hora_actual))

        proximas_qs = base.filter(fecha__gt=hoy)
        if dias is not None:
            proximas_qs = proximas_qs.filter(fecha__lte=hoy + timedelta(days=dias))
        proximas = ordenar(proximas_qs)

        grupos = {
            "vencidas": self.get_serializer(vencidas, many=True).data,
            "para_hoy": self.get_serializer(para_hoy, many=True).data,
            "proximas": self.get_serializer(proximas, many=True).data,
        }
        return Response({
            "fecha": hoy.isoformat(),
            "hora": hora_actual.strftime("%H:%M"),
            "filtros": {"estado": estado, "orden": orden, "dias": dias},
            "resumen": {nombre: len(items) for nombre, items in grupos.items()},
            "grupos": grupos,
        })

class PreferenciasView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/preferencias/

    Preferencias del usuario autenticado. Si todavía no tiene, se crean
    con los valores por defecto (límite de 6 horas al día).
    """
    serializer_class = PreferenciasSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return PreferenciasUsuario.de_usuario(self.request.user)

    @extend_schema(
        tags=["preferencias"],
        summary="Ver preferencias del usuario",
        responses={
            200: PreferenciasSerializer,
            401: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Falta el token de autenticación.",
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        tags=["preferencias"],
        summary="Actualizar preferencias del usuario",
        description="Cambia el límite de horas al día (entre 1 y 12, pasos de 0.5 en el formulario).",
        request=PreferenciasSerializer,
        responses={
            200: PreferenciasSerializer,
            400: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Límite fuera del rango 1–12 o no numérico.",
            ),
            401: OpenApiResponse(
                response=ErrorRespuestaSerializer,
                description="Falta el token de autenticación.",
            ),
        },
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)