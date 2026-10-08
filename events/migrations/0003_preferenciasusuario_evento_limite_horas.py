import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_evento_usuario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='evento',
            name='limite_horas',
            field=models.DecimalField(
                decimal_places=2,
                default=6,
                help_text='Límite de horas al día definido para este evento (entre 1 y 12)',
                max_digits=4,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(12),
                ],
            ),
        ),
        migrations.CreateModel(
            name='PreferenciasUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('limite_horas', models.DecimalField(
                    decimal_places=2,
                    default=6,
                    help_text='Límite de horas de trabajo al día (entre 1 y 12, por defecto 6)',
                    max_digits=4,
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(12),
                    ],
                )),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='preferencias',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'preferencias de usuario',
                'verbose_name_plural': 'preferencias de usuarios',
            },
        ),
    ]