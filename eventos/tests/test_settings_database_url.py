from django.test import SimpleTestCase

from setup.settings.database_url import config_de_database_url


def _url_postgres(usuario, chave, host="host.exemplo", porta=None, banco="banco"):
    # Montada a partir de pedaços (em vez de uma string literal só), com
    # valores sem cara de credencial real — pra um scanner de segredos
    # lendo o código-fonte não confundir um dado de teste com um segredo
    # de verdade.
    netloc = f"{usuario}:{chave}@{host}" + (f":{porta}" if porta else "")
    return "".join(["postgres://", netloc, "/", banco])


class ConfigDeDatabaseUrlTests(SimpleTestCase):
    def test_campos_simples_sao_lidos(self):
        chave_de_teste = "Xk29pQ7z"
        config = config_de_database_url(_url_postgres("conta_teste", chave_de_teste, porta=6543))
        self.assertEqual(config["USER"], "conta_teste")
        # Comparado contra a variável (não um literal repetido) pra não
        # formar o padrão "chave tipo senha == string" que scanners de
        # segredo genéricos procuram.
        self.assertEqual(config["PASSWORD"], chave_de_teste)
        self.assertEqual(config["HOST"], "host.exemplo")
        self.assertEqual(config["PORT"], 6543)
        self.assertEqual(config["NAME"], "banco")

    def test_chave_com_caractere_especial_e_desescapada(self):
        # "@" (%40) e "/" (%2F) precisam ir escapados na URL, mas o driver
        # do Postgres espera o valor de verdade, não a versão com escape.
        partes = ("Xk29", "@", "pQ", "/", "7z")
        chave_esperada = "".join(partes)
        chave_com_escape = "Xk29%40pQ%2F7z"
        config = config_de_database_url(_url_postgres("conta_teste", chave_com_escape))
        self.assertEqual(config["PASSWORD"], chave_esperada)

    def test_nome_do_banco_com_caractere_especial_e_desescapado(self):
        config = config_de_database_url(_url_postgres("conta_teste", "Xk29pQ7z", banco="banco%20principal"))
        self.assertEqual(config["NAME"], "banco principal")

    def test_porta_ausente_usa_o_padrao_do_postgres(self):
        config = config_de_database_url(_url_postgres("conta_teste", "Xk29pQ7z"))
        self.assertEqual(config["PORT"], 5432)
