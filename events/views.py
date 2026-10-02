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
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from .models import Evento, Gestion

from .serializers import (
    AuthRespuestaSerializer,
    ErrorRespuestaSerializer,
    EventoSerializer,
    GestionHoySerializer,
    GestionSerializer,
    HoyRespuestaSerializer,
    LoginSerializer,
    RegistroSerializer,
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

    Solo se ven las gestiones de eventos que pertenecen al usuario.

    El POST plano requiere 'evento' en el body (id del evento al que
    pertenece). Para agregar una gestión a un evento ya identificado en
    la UI, es más cómodo usar POST /api/eventos/<id>/subtareas/ de arriba.

    El resto (marcarGestion, guardarNota, reprogramarGestion,
    posponerGestion) son PATCH sobre una gestión existente.
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
        # Solo se puede agregar gestiones a eventos propios
        evento = get_object_or_404(
            Evento, pk=evento_id, usuario=self.request.user
        )
        serializer.save(evento=evento)



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