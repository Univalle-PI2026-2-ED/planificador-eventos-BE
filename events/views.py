from rest_framework import viewsets
from rest_framework.decorators import api_view
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
    """
    queryset = Evento.objects.all().prefetch_related("gestiones")
    serializer_class = EventoSerializer


class GestionViewSet(viewsets.ModelViewSet):
    """
    GET /api/gestiones/
    GET/PATCH/PUT/DELETE /api/gestiones/<id>/

    Cubre marcarGestion, guardarNota, reprogramarGestion y posponerGestion
    del frontend, que son todos PATCH sobre una gestión existente.
    """
    queryset = Gestion.objects.select_related("evento").all()
    serializer_class = GestionSerializer
    http_method_names = ["get", "patch", "put", "delete", "head", "options"]