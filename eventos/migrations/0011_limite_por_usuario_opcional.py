import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("eventos", "0010_alter_evento_resumo")]

    operations = [
        migrations.AlterField(
            model_name="evento",
            name="limite_por_usuario",
            field=models.PositiveSmallIntegerField(
                blank=True,
                default=10,
                help_text="Máximo de ingressos que uma mesma pessoa pode reservar neste evento.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
