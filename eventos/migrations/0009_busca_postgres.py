"""Índices de busca do PostgreSQL.

A coluna Evento.busca_texto já guarda o texto normalizado (minúsculo, sem
acento). Isso resolve a correção da busca em qualquer banco. O que falta é
velocidade: `LIKE '%termo%'` não usa índice B-tree.

No PostgreSQL, um índice GIN com pg_trgm faz esse LIKE usar índice. No SQLite
não existe equivalente, e a migration simplesmente não faz nada — o projeto
continua funcionando, só sem o ganho de desempenho.

`unaccent` é instalado junto porque a busca full-text (services/busca.py, ramo
PostgreSQL) depende dela.
"""

from django.db import migrations

SQL_POSTGRES = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
    "CREATE EXTENSION IF NOT EXISTS unaccent;",
    "CREATE INDEX IF NOT EXISTS eventos_eve_busca_trgm "
    "ON eventos_evento USING gin (busca_texto gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS eventos_loc_nome_trgm "
    "ON eventos_local USING gin (nome_normalizado gin_trgm_ops);",
    "CREATE INDEX IF NOT EXISTS eventos_pro_nome_trgm "
    "ON eventos_produtor USING gin (nome_normalizado gin_trgm_ops);",
]

SQL_POSTGRES_REVERSO = [
    "DROP INDEX IF EXISTS eventos_pro_nome_trgm;",
    "DROP INDEX IF EXISTS eventos_loc_nome_trgm;",
    "DROP INDEX IF EXISTS eventos_eve_busca_trgm;",
]


def _executar(schema_editor, comandos):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for comando in comandos:
            try:
                cursor.execute(comando)
            except Exception as erro:  # pragma: no cover
                # CREATE EXTENSION exige superusuário em algumas hospedagens.
                # Falhar aqui não pode impedir o deploy: a busca continua
                # correta, apenas sem o índice.
                import logging

                logging.getLogger("eventos").warning(
                    "Índice de busca não pôde ser criado (%s): %s", comando.split()[0], erro
                )


def aplicar(apps, schema_editor):
    _executar(schema_editor, SQL_POSTGRES)


def reverter(apps, schema_editor):
    _executar(schema_editor, SQL_POSTGRES_REVERSO)


class Migration(migrations.Migration):

    atomic = False  # CREATE EXTENSION não convive bem com transação em alguns provedores.

    dependencies = [("eventos", "0008_migrar_locais_e_produtores")]

    operations = [migrations.RunPython(aplicar, reverter)]
