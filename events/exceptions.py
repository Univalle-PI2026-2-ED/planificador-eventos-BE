import logging
import uuid

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

# Mensajes en español, sin jerga técnica, para que el frontend los pueda
# mostrar directo al organizador sin traducirlos.
_FRIENDLY_MESSAGES = {
    400: "Revisa los datos enviados, algo no es válido.",
    401: "Debes iniciar sesión para hacer esto.",
    403: "No tienes permiso para hacer esto.",
    404: "No se encontró el recurso solicitado.",
    405: "Ese método no está permitido en este endpoint.",
    409: "Ese día superaría tu límite de horas diario.",
    429: "Demasiadas solicitudes, intenta de nuevo en un momento.",
    500: "Ocurrió un error inesperado en el servidor.",
}

# Código interno estable por tipo de error, para que el frontend (o quien
# revise los logs) identifique el caso sin depender del texto del mensaje.
_CODIGOS_ERROR = {
    400: "VALIDATION_ERROR",
    401: "NOT_AUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "DAILY_LIMIT_EXCEEDED",
    429: "THROTTLED",
    500: "INTERNAL_ERROR",
}


class ConflictoSobrecarga(APIException):
    """409: reprogramar una gestión haría que el día destino pase el límite de horas.

    Recibe un dict con fecha, horas, limite, exceso y gestiones. Se guarda tal
    cual en `detail` (DRF lo convertiría todo a texto) para que los números
    lleguen al frontend como números.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "El día destino supera el límite de horas."
    default_code = "sobrecarga_diaria"

    def __init__(self, detalle):
        super().__init__(detail=detalle)
        self.detail = detalle


def custom_exception_handler(exc, context):
    """Envuelve todos los errores de la API en un shape consistente:

    {
        "success": false,
        "error": {
            "status": 404,
            "code": "NOT_FOUND",
            "message": "No se encontró el recurso solicitado.",
            "trace_id": "3f2b9c1e8a7d4f6b9e0c1a2b3c4d5e6f",
            "details": <lo que DRF generó originalmente, campo por campo>
        }
    }

    - code: código interno estable del tipo de error.
    - trace_id: identificador único de esta falla; también va en el header
      X-Trace-Id y queda en los logs del servidor para poder rastrearla.
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        # Excepción no manejada por DRF (bug real de 500). La dejamos pasar
        # tal cual para no ocultar errores inesperados en desarrollo/logs.
        return response

    trace_id = uuid.uuid4().hex
    codigo = _CODIGOS_ERROR.get(response.status_code, "ERROR")
    message = _FRIENDLY_MESSAGES.get(
        response.status_code, "Ocurrió un error al procesar la solicitud."
    )

    request = context.get("request")
    logger.warning(
        "API error %s %s trace_id=%s path=%s",
        response.status_code,
        codigo,
        trace_id,
        getattr(request, "path", "-"),
    )

    response.data = {
        "success": False,
        "error": {
            "status": response.status_code,
            "code": codigo,
            "message": message,
            "trace_id": trace_id,
            "details": response.data,
        },
    }
    response["X-Trace-Id"] = trace_id
    return response