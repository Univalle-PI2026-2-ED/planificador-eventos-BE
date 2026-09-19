from django.db import models


class Evento(models.Model):
    """Un evento con su plan de trabajo (gestiones logísticas).

    Coincide con el shape que espera EventosContext.jsx en el frontend:
    { id, nombre, fecha, gestiones: [...] }
    """

    nombre = models.CharField(max_length=200)
    fecha = models.DateField(help_text="Fecha del evento (YYYY-MM-DD)")
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