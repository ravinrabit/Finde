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
            cursor.execute("SHOW search_path;")
            self.stdout.write(f"search_path: {cursor.fetchone()[0]}")

            cursor.execute(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema');"
            )
            antes = cursor.fetchall()
            self.stdout.write(f"Tabelas em qualquer schema antes do reset: {list(antes)}")

            schemas_para_limpar = {linha[0] for linha in antes} | {"public"}
            for schema in schemas_para_limpar:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
            cursor.execute("CREATE SCHEMA public;")
            cursor.execute("GRANT ALL ON SCHEMA public TO CURRENT_USER;")
            cursor.execute("GRANT ALL ON SCHEMA public TO public;")

            cursor.execute(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema');"
            )
            depois = cursor.fetchall()

        connection.commit()

        if depois:
            raise CommandError(
                f"Ainda restou tabela depois do reset: {list(depois)}. "
                "Verifique permissões do usuário do banco (precisa ser dono dos schemas)."
            )

        self.stdout.write(self.style.SUCCESS("Todos os schemas limpos e confirmados vazios."))
