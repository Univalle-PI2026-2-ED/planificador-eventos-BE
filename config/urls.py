from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Raíz: al abrir el dominio pelado, manda directo a la doc interactiva
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),

    path("admin/", admin.site.urls),

    # API
    path("api/", include("events.urls")),

    # OpenAPI / Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]