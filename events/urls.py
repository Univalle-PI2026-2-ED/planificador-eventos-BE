from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EventoViewSet, GestionViewSet, HoyView, LoginView, RegistroView, health_check


router = DefaultRouter()
router.register("eventos", EventoViewSet, basename="evento")
router.register("gestiones", GestionViewSet, basename="gestion")

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("auth/registro/", RegistroView.as_view(), name="registro"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("hoy/", HoyView.as_view(), name="hoy"),
    path("", include(router.urls)),
]