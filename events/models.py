from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Mismo rango y valor por defecto que el formulario del frontend (Crear.jsx)
LIMITE_HORAS_DEFECTO = 6
LIMITE_HORAS_MIN = 1
LIMITE_HORAS_MAX = 12

def validar_paso_media_hora(value):
    """El límite debe aumentar en pasos de 0,5 horas."""
    if (Decimal(value) * 2) % 1 != 0:
        raise ValidationError(
            "El límite debe configurarse en incrementos de 0,5 horas."
        )

def campo_limite_horas(help_text):
    return models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=LIMITE_HORAS_DEFECTO,
        validators=[
            MinValueValidator(LIMITE_HORAS_MIN),
            MaxValueValidator(LIMITE_HORAS_MAX),
            validar_paso_media_hora,
        ],
        help_text=help_text,
    )


class PreferenciasUsuario(models.Model):
    """Preferencias de cada usuario (por ahora, su límite de horas al día)."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferencias",
    )
    limite_horas = campo_limite_horas(
        "Límite de horas de trabajo al día (entre 1 y 12, por defecto 6)"
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "preferencias de usuario"
        verbose_name_plural = "preferencias de usuarios"

    def __str__(self):
        return f"Preferencias de {self.usuario}"

    @classmethod
    def de_usuario(cls, usuario):
        """Devuelve las preferencias del usuario; las crea con valores por defecto si no existen."""
        preferencias, _ = cls.objects.get_or_create(usuario=usuario)
        return preferencias


class Evento(models.Model):
    """Un evento con su plan de trabajo (gestiones logísticas).

    Coincide con la estructura que utiliza el frontend:
    { id, nombre, fecha, gestiones: [...] }
    """

    nombre = models.CharField(max_length=200)
    fecha = models.DateField(help_text="Fecha del evento (YYYY-MM-DD)")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eventos",
        null=True,
        blank=True,
        help_text="Dueño del evento",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha"]

    def __str__(self):
        return self.nombre


class Gestion(models.Model):
    """Una gestión (tarea) dentro del plan de trabajo de un evento."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        HECHO = "hecho", "Hecho"
        POSPUESTO = "pospuesto", "Pospuesto"

    evento = models.ForeignKey(
        Evento, on_delete=models.CASCADE, related_name="gestiones"
    )
    nombre = models.CharField(max_length=200)
    fecha = models.DateField(help_text="Día en que se hará la gestión (YYYY-MM-DD)")
    hora = models.TimeField(help_text="Hora de la gestión (HH:MM)")
    horas = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text="Horas estimadas que tomará (entre 0.5 y 8)",
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    nota = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["fecha", "hora"]

    def __str__(self):
        return f"{self.nombre} ({self.evento.nombre})"