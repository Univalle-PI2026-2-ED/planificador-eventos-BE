from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Evento, Gestion
from .serializers import EventoSerializer, GestionSerializer


@api_view(["GET"])
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
    """
    queryset = Evento.objects.all().prefetch_related("gestiones")
    serializer_class = EventoSerializer

    @action(detail=True, methods=["post"], url_path="subtareas")
    def subtareas(self, request, pk=None):
        """Agrega una gestión (subtarea logística) a un evento que ya existe.

        Cubre US-02 Escenario 1: 'Dado que existe un evento, cuando agrego
        una subtarea logística con datos válidos, entonces el sistema
        guarda la subtarea logística asociada al evento'.
        """
        evento = self.get_object()
        serializer = GestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(evento=evento)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GestionViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/gestiones/
    GET/PATCH/PUT/DELETE /api/gestiones/<id>/

    El POST plano requiere 'evento' en el body (id del evento al que
    pertenece). Para agregar una gestión a un evento ya identificado en
    la UI, es más cómodo usar POST /api/eventos/<id>/subtareas/ de arriba.

    El resto (marcarGestion, guardarNota, reprogramarGestion,
    posponerGestion) son PATCH sobre una gestión existente.
    """
    queryset = Gestion.objects.select_related("evento").all()
    serializer_class = GestionSerializer

    def perform_create(self, serializer):
        evento_id = self.request.data.get("evento")
        if not evento_id:
            raise ValidationError({
                "evento": [
                    "Este campo es obligatorio. Indica el id del evento, "
                    "o usa POST /api/eventos/<id>/subtareas/ en su lugar."
                ]
            })
        evento = get_object_or_404(Evento, pk=evento_id)
        serializer.save(evento=evento)