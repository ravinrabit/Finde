from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "APAGA TODO O ESQUEMA do banco Postgres atual (DROP SCHEMA public CASCADE) "
        "e recria vazio, para o migrate rodar do zero. Uso único — remova do comando "
        "de build depois de rodar uma vez. Nunca roda fora do Postgres."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar", action="store_true", help="Obrigatório: confirma que é para apagar tudo."
        )

    def handle(self, *args, **opcoes):
        if connection.vendor != "postgresql":
            self.stdout.write("Banco atual não é Postgres — nada a fazer.")
            return

        if not opcoes["confirmar"]:
            raise CommandError(
                "Isso apaga TODAS as tabelas do banco atual. Rode de novo com --confirmar "
                "se tiver certeza que não há dado nenhum para perder."
            )

        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE;")
            cursor.execute("CREATE SCHEMA public;")

        self.stdout.write(self.style.SUCCESS("Esquema do Postgres limpo. Rode 'migrate' em seguida."))
