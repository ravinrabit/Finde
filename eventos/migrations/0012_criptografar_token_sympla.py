from django.db import migrations, models


def recriptografar_tokens(apps, schema_editor):
    IntegracaoSympla = apps.get_model("eventos", "IntegracaoSympla")
    for integracao in IntegracaoSympla.objects.all():
        integracao.save(update_fields=["token"])


def descriptografar_tokens(apps, schema_editor):
    IntegracaoSympla = apps.get_model("eventos", "IntegracaoSympla")
    with schema_editor.connection.cursor() as cursor:
        for integracao in IntegracaoSympla.objects.all():
            cursor.execute(
                "UPDATE eventos_integracaosympla SET token = %s WHERE id = %s",
                [integracao.token, integracao.pk],
            )


class Migration(migrations.Migration):

    dependencies = [
        ("eventos", "0011_limite_por_usuario_opcional"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integracaosympla",
            name="token",
            field=models.CharField(max_length=1024),
        ),
        migrations.RunPython(recriptografar_tokens, descriptografar_tokens),
    ]
