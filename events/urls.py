from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EventoViewSet, GestionViewSet, health_check

router = DefaultRouter()
router.register("eventos", EventoViewSet, basename="evento")
router.register("gestiones", GestionViewSet, basename="gestion")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("", include(router.urls)),
]