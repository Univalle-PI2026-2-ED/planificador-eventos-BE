from rest_framework.views import exception_handler as drf_exception_handler

# Mensajes en español, sin jerga técnica, para que el frontend los pueda
# mostrar directo al organizador sin traducirlos.
_FRIENDLY_MESSAGES = {
    400: "Revisa los datos enviados, algo no es válido.",
    401: "Debes iniciar sesión para hacer esto.",
    403: "No tienes permiso para hacer esto.",
    404: "No se encontró el recurso solicitado.",
    405: "Ese método no está permitido en este endpoint.",
    429: "Demasiadas solicitudes, intenta de nuevo en un momento.",
    500: "Ocurrió un error inesperado en el servidor.",
}


def custom_exception_handler(exc, context):
    """Envuelve todos los errores de la API en un shape consistente:

    {
        "success": false,
        "error": {
            "status": 404,
            "message": "No se encontró el recurso solicitado.",
            "details": <lo que DRF generó originalmente, campo por campo>
        }
    }

    Así el frontend siempre puede leer response.data.error.message sin
    importar cuál endpoint falló.
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        # Excepción no manejada por DRF (bug real de 500). La dejamos pasar
        # tal cual para no ocultar errores inesperados en desarrollo/logs.
        return response

    message = _FRIENDLY_MESSAGES.get(
        response.status_code, "Ocurrió un error al procesar la solicitud."
    )

    response.data = {
        "success": False,
        "error": {
            "status": response.status_code,
            "message": message,
            "details": response.data,
        },
    }
    return response