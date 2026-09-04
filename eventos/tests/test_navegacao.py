"""Paginação, ordenação, destaques e páginas de faceta.

Cada teste aqui corresponde a um bug real da auditoria. O comentário diz qual.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento
from .base import criar_evento


class PaginacaoTests(TestCase):
    """BUG 1 — href="?{% querystring page=2 %}" gerava "??page=2".

    A tag já devolve a string com "?" na frente. Com o "?" extra, o servidor
    lia a chave "?page" e o parâmetro "page" nunca chegava: a paginação
    mostrava sempre a primeira página, em todas as listagens do site.
    """

    @classmethod
    def setUpTestData(cls):
        base = timezone.now() + timedelta(days=3)
        for indice in range(20):
            criar_evento(nome=f"Evento {indice:02d}", data=base + timedelta(hours=indice))

    def test_pagina_dois_traz_resultados_diferentes(self):
        primeira = self.client.get(reverse("lista_eventos"))
        segunda = self.client.get(reverse("lista_eventos"), {"page": 2})

        nomes_1 = {e.nome for e in primeira.context["eventos"]}
        nomes_2 = {e.nome for e in segunda.context["eventos"]}

        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.context["pagina"].number, 2)
        self.assertTrue(nomes_2)
        self.assertFalse(nomes_1 & nomes_2, "página 2 repetiu itens da página 1")

    def test_link_da_paginacao_nao_tem_interrogacao_dupla(self):
        resposta = self.client.get(reverse("lista_eventos"))
        html = resposta.content.decode()
        self.assertNotIn('href="??', html)
        self.assertIn("page=2", html)

    def test_paginacao_preserva_os_filtros(self):
        resposta = self.client.get(reverse("lista_eventos"), {"categoria": Categoria.MUSICA})
        html = resposta.content.decode()
        if "page=2" in html:
            self.assertIn("categoria=musica", html)

    def test_pagina_alem_do_fim_cai_na_ultima(self):
        resposta = self.client.get(reverse("lista_eventos"), {"page": 999})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.context["pagina"].number,
            resposta.context["pagina"].paginator.num_pages,
        )

    def test_pagina_nao_numerica_nao_derruba(self):
        resposta = self.client.get(reverse("lista_eventos"), {"page": "abacaxi"})
        self.assertEqual(resposta.status_code, 200)


class OrdenacaoTests(TestCase):
    """BUG 2 — a página tem dois formulários [data-filtros-form] e o JS usava
    querySelector, que devolve só o primeiro. O select "Ordenar por" nunca
    disparava o envio. O JS foi corrigido; aqui garantimos o lado do servidor.
    """

    @classmethod
    def setUpTestData(cls):
        agora = timezone.now()
        cls.caro = criar_evento(nome="Caro", preco=Decimal("300.00"), data=agora + timedelta(days=2))
        cls.barato = criar_evento(nome="Barato", preco=Decimal("20.00"), data=agora + timedelta(days=9))
        cls.gratis = criar_evento(nome="Grátis", gratuito=True, preco=None, data=agora + timedelta(days=6))

    def nomes(self, **parametros):
        resposta = self.client.get(reverse("lista_eventos"), parametros)
        return [e.nome for e in resposta.context["eventos"]]

    def test_ordenar_por_data_e_o_padrao(self):
        self.assertEqual(self.nomes(), ["Caro", "Grátis", "Barato"])

    def test_ordenar_por_preco(self):
        self.assertEqual(self.nomes(ordenar="preco")[0], "Grátis")

    def test_ordenar_por_recentes(self):
        nomes = self.nomes(ordenar="recentes")
        self.assertEqual(len(nomes), 3)
        self.assertEqual(nomes[0], "Grátis")

    def test_ordenacao_desconhecida_cai_no_padrao(self):
        self.assertEqual(self.nomes(ordenar="alfabetica"), ["Caro", "Grátis", "Barato"])

    def test_o_formulario_de_ordenar_preserva_os_filtros_ativos(self):
        resposta = self.client.get(reverse("lista_eventos"), {"categoria": Categoria.MUSICA})
        html = resposta.content.decode()
        self.assertIn('name="categoria"', html)
        self.assertIn('data-filtros-form', html)


class DestaquesTests(TestCase):
    """BUG 3 — a home buscava 3 destaques, o template renderizava só
    `destaques.0`, e "em breve" excluía os três. Dois eventos marcados como
    destaque simplesmente sumiam do site.
    """

    @classmethod
    def setUpTestData(cls):
        agora = timezone.now()
        for indice in range(3):
            criar_evento(
                nome=f"Destaque {indice}",
                destaque=True,
                imagem_url="https://exemplo.test/capa.jpg",
                data=agora + timedelta(days=indice + 1),
            )
        for indice in range(4):
            criar_evento(nome=f"Comum {indice}", data=agora + timedelta(days=indice + 10))

    def test_todos_os_destaques_aparecem_na_home(self):
        resposta = self.client.get(reverse("home"))
        exibidos = {resposta.context["destaque_principal"].nome}
        exibidos |= {e.nome for e in resposta.context["destaques_secundarios"]}
        exibidos |= {e.nome for e in resposta.context["em_breve"]}

        for indice in range(3):
            self.assertIn(f"Destaque {indice}", exibidos)

    def test_destaque_principal_nao_se_repete_em_breve(self):
        resposta = self.client.get(reverse("home"))
        principal = resposta.context["destaque_principal"]
        nomes = [e.nome for e in resposta.context["em_breve"]]
        self.assertNotIn(principal.nome, nomes)

    def test_home_sem_destaque_marcado_usa_eventos_com_capa(self):
        Evento.objects.update(destaque=False)
        resposta = self.client.get(reverse("home"))
        self.assertIsNotNone(resposta.context["destaque_principal"])

    def test_home_vazia_nao_quebra(self):
        Evento.objects.all().delete()
        resposta = self.client.get(reverse("home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.context["destaque_principal"])


class FacetasTests(TestCase):
    """Páginas de faceta com caminho próprio, título e canônica próprios —
    no lugar das 52 querystrings duplicadas que iam para o sitemap."""

    @classmethod
    def setUpTestData(cls):
        criar_evento(nome="Show na Ceilândia", categoria=Categoria.SHOWS, regiao=Regiao.CEILANDIA)
        criar_evento(nome="Cinema na Asa Sul", categoria=Categoria.CINEMA, regiao=Regiao.ASA_SUL)
        criar_evento(nome="Feira grátis", gratuito=True, preco=None, regiao=Regiao.GAMA)

    def test_pagina_de_categoria_filtra(self):
        resposta = self.client.get(reverse("eventos_categoria", args=["shows"]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([e.nome for e in resposta.context["eventos"]], ["Show na Ceilândia"])

    def test_pagina_de_categoria_tem_titulo_proprio(self):
        resposta = self.client.get(reverse("eventos_categoria", args=["cinema"]))
        self.assertIn("Cinema em Brasília", resposta.context["titulo_pagina"])
        self.assertTrue(resposta.context["descricao_pagina"])

    def test_categoria_inexistente_devolve_404(self):
        resposta = self.client.get("/eventos/categoria/nao-existe/")
        self.assertEqual(resposta.status_code, 404)

    def test_pagina_de_regiao_filtra(self):
        resposta = self.client.get(reverse("eventos_regiao", args=["ceilandia"]))
        self.assertEqual([e.nome for e in resposta.context["eventos"]], ["Show na Ceilândia"])

    def test_pagina_de_gratuitos(self):
        resposta = self.client.get(reverse("eventos_gratuitos"))
        self.assertEqual([e.nome for e in resposta.context["eventos"]], ["Feira grátis"])

    def test_facetas_tem_canonica_propria(self):
        resposta = self.client.get(reverse("eventos_regiao", args=["gama"]))
        self.assertIn("/eventos/regiao/gama/", resposta.context["canonica"])

    def test_sitemap_nao_repete_a_mesma_pagina_com_querystring(self):
        resposta = self.client.get("/sitemap.xml")
        corpo = resposta.content.decode()
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("?categoria=", corpo)
        self.assertIn("/eventos/categoria/shows/", corpo)


class BuscaTests(TestCase):
    """A busca passou a consultar uma coluna normalizada, o que a torna
    tolerante a acento e caixa em SQLite e em PostgreSQL."""

    @classmethod
    def setUpTestData(cls):
        criar_evento(nome="Rock no Cerrado", local="Casa do Cantador")
        criar_evento(nome="Mostra de Cinema", local="Cine Brasília")
        criar_evento(nome="Feira gastronômica", local="Parque da Cidade")

    def nomes(self, termo):
        resposta = self.client.get(reverse("lista_eventos"), {"q": termo})
        return [e.nome for e in resposta.context["eventos"]]

    def test_busca_ignora_caixa(self):
        for termo in ("rock", "Rock", "ROCK"):
            self.assertEqual(self.nomes(termo), ["Rock no Cerrado"], termo)

    def test_busca_ignora_acento_na_consulta(self):
        self.assertEqual(self.nomes("gastronomica"), ["Feira gastronômica"])
        self.assertEqual(self.nomes("gastronômica"), ["Feira gastronômica"])

    def test_busca_ignora_acento_no_conteudo(self):
        self.assertEqual(self.nomes("brasilia"), ["Mostra de Cinema"])
        self.assertEqual(self.nomes("brasília"), ["Mostra de Cinema"])

    def test_varios_termos_precisam_casar_todos(self):
        self.assertEqual(self.nomes("mostra cinema"), ["Mostra de Cinema"])
        self.assertEqual(self.nomes("mostra jazz"), [])

    def test_termo_de_uma_letra_e_ignorado(self):
        self.assertEqual(len(self.nomes("a")), 3)
