"""limite_por_usuario deixa de ser obrigatório no formulário.

O campo tem `default=10`, mas sem `blank=True` o Django o trata como
obrigatório em todo ModelForm e no admin. Como ele foi acrescentado nesta
evolução, passou a exigir preenchimento de quem já enviava o formulário de
evento sem ele — uma regressão.

`blank` não altera o schema: é só validação. A migration existe para o estado
declarado bater com o modelo.
"""

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
