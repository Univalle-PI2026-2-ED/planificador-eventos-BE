# Chronos — Planificador de eventos (Backend / API)

API REST del planificador de eventos para organizadores independientes. Gestiona
usuarios, eventos, gestiones logísticas, la vista "Hoy", la detección de
sobrecarga diaria al reprogramar y el progreso de preparación de cada evento.

- **Estado de la API:** https://planificador-eventos-be.onrender.com/api/health/
- **Documentación interactiva (Swagger):** https://planificador-eventos-be.onrender.com/api/docs/
- **App publicada (frontend):** https://planificador-eventos-fe.vercel.app
- **Repositorio del frontend:** [link-al-repo-frontend]

> El backend está en el plan gratuito de Render: si lleva rato sin uso, la primera
> petición puede tardar hasta 1 minuto en responder. Espera y vuelve a intentar.

## Cuenta de prueba
- Usuario: `[usuario-demo]`
- Correo: `[correo-demo]`
- Contraseña: `[contraseña-demo]`

La cuenta ya tiene eventos y gestiones cargados.

## Cómo probar la API en Swagger
1. Abre https://planificador-eventos-be.onrender.com/api/docs/
2. En `POST /api/auth/login/` pulsa **Try it out** y envía:
```json
   { "email": "[correo-demo]", "password": "[contraseña-demo]" }
```
   (también acepta `"username"` en lugar de `"email"`).
3. Copia el `token` de la respuesta, pulsa **Authorize** (arriba a la derecha) y
   escribe: `Token <tu-token>` (con la palabra `Token`, un espacio y el token).
4. Ya puedes probar el resto de endpoints, por ejemplo:
   - `GET /api/hoy/`: gestiones agrupadas en vencidas, para hoy y próximas.
   - `GET /api/eventos/`: eventos con su progreso.
   - `POST /api/gestiones/{id}/reprogramar/`: mueve una gestión a un día con
     muchas horas para ver el **409** de sobrecarga.
5. Para ver los errores estándar:
   - **401:** pulsa *Logout* en Authorize y llama a `GET /api/eventos/`.
   - **404:** `GET /api/eventos/999999/`.
   - **400:** `PATCH /api/preferencias/` con `{ "limite_horas": 20 }`.

## Tecnologías
Python 3.13, Django 6.1, Django REST Framework, drf-spectacular (Swagger),
PostgreSQL (Supabase), autenticación por token, Gunicorn, desplegado en Render.

## Estructura
```
planificador-eventos-BE/
├── config/            # Configuración del proyecto (settings, urls, wsgi)
├── events/            # App principal
│   ├── models.py      # Evento, Gestion, PreferenciasUsuario
│   ├── serializers.py # Validaciones y formato de entrada/salida
│   ├── views.py       # Endpoints
│   ├── urls.py        # Rutas de /api/
│   ├── exceptions.py  # Formato estándar de errores
│   ├── tests.py       # Pruebas de endpoints
│   └── migrations/
├── manage.py
├── requirements.txt
└── schema.yml         # Esquema OpenAPI exportado
```

## Modelo de datos
- **User** (Django): usuario/organizador.
- **PreferenciasUsuario** (1–1 con User): `limite_horas` diario (1 a 16, pasos
  de 0,5; por defecto 6).
- **Evento** (N–1 con User): `nombre`, `fecha`.
- **Gestion** (N–1 con Evento): `nombre`, `fecha`, `hora`, `horas` (0,5 a 16),
  `estado` (`pendiente` | `hecho` | `pospuesto`), `nota`, `fecha_cierre`.

Cada usuario solo ve y modifica sus propios eventos y gestiones.

## Endpoints principales
Todos requieren el header `Authorization: Token <token>`, salvo health, registro
y login.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health/` | Estado de la API |
| POST | `/api/auth/registro/` | Crear cuenta (devuelve token) |
| POST | `/api/auth/login/` | Iniciar sesión (devuelve token) |
| GET / PATCH | `/api/preferencias/` | Ver / cambiar el límite diario de horas |
| GET / POST | `/api/eventos/` | Listar / crear eventos (con sus gestiones) |
| GET / PATCH / PUT / DELETE | `/api/eventos/{id}/` | Detalle, editar, eliminar evento |
| POST | `/api/eventos/{id}/subtareas/` | Agregar una gestión a un evento |
| GET / PATCH / DELETE | `/api/gestiones/{id}/` | Detalle, editar (estado, nota…), eliminar gestión |
| POST | `/api/gestiones/{id}/reprogramar/` | Mover gestión validando el límite diario (409 si se pasa) |
| GET | `/api/hoy/` | Gestiones agrupadas por urgencia (`?estado=`, `?orden=`, `?dias=`) |

La documentación completa con ejemplos está en Swagger.

## Formato de errores
Todos los errores responden con la misma estructura:
```json
{
  "success": false,
  "error": {
    "status": 400,
    "message": "Revisa los datos enviados, algo no es válido.",
    "details": { "limite_horas": ["El límite no puede superar 16 horas al día."] }
  }
}
```
| Código | Cuándo |
|---|---|
| 400 | Datos inválidos o campos faltantes |
| 401 | Falta el token o es inválido |
| 404 | El recurso no existe o es de otro usuario |
| 409 | Reprogramar superaría el límite diario de horas |

## Cómo correrlo en local
1. Instala Python 3.12 o superior.
2. Clona el repositorio y entra a la carpeta:
```bash
   git clone [link-al-repo-backend]
   cd planificador-eventos-BE
```
3. Crea y activa un entorno virtual:
```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
```
4. Instala dependencias:
```bash
   pip install -r requirements.txt
```
5. Crea un archivo `.env` en la raíz. Para probar rápido con SQLite:
```
   USE_SQLITE=True
   DEBUG=True
   SECRET_KEY=cualquier-clave-local
```
   Para usar PostgreSQL:
```
   SECRET_KEY=tu-clave-secreta
   DEBUG=True
   DB_NAME=postgres
   DB_USER=tu-usuario
   DB_PASSWORD=tu-contraseña
   DB_HOST=tu-host
   DB_PORT=5432
```
6. Aplica las migraciones y arranca el servidor:
```bash
   python manage.py migrate
   python manage.py runserver
```
7. Abre http://localhost:8000/api/docs/

## Pruebas
```bash
# Windows (PowerShell)
$env:USE_SQLITE="True"; python manage.py test
# macOS / Linux
USE_SQLITE=True python manage.py test
```

## Variables de entorno
| Variable | Descripción | Por defecto |
|---|---|---|
| `SECRET_KEY` | Clave secreta de Django | `dev-secret-key-change-me` |
| `DEBUG` | Modo depuración (`False` en producción) | `True` |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por coma | `localhost,127.0.0.1` |
| `USE_SQLITE` | `True` para usar SQLite en local | `False` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Conexión a PostgreSQL | — |

En Render, `RENDER_EXTERNAL_HOSTNAME` se agrega solo a `ALLOWED_HOSTS`.

## Despliegue (Render)
- **Build command:** `pip install -r requirements.txt && python manage.py migrate`
- **Start command:** `gunicorn config.wsgi:application`
- Variables de entorno: las de la tabla anterior, con `DEBUG=False`.
- CORS permite `http://localhost:5173` y `https://planificador-eventos-fe.vercel.app`.

## Equipo
- Daniel Andrés Micolta Góngora
- Thomas Herrera Parra — BackEnd Lead
- Yoel Steven Montoya Hernández
- Andrés Felipe Muñoz Castro
