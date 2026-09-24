import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento
from .base import criar_evento, criar_usuario


class PaginacaoTests(TestCase):
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


class DestaquePagoTests(TestCase):
    def nomes(self, **parametros):
        resposta = self.client.get(reverse("lista_eventos"), parametros)
        return [e.nome for e in resposta.context["eventos"]]

    def test_plano_pago_ativo_fica_na_frente_mesmo_com_data_mais_distante(self):
        from ..constants import PlanoDestaque

        agora = timezone.now()
        criar_evento(nome="Comum mais cedo", data=agora + timedelta(days=1))
        criar_evento(
            nome="Pago mais tarde",
            data=agora + timedelta(days=10),
            plano_destaque=PlanoDestaque.PREMIUM,
            destaque_pago_ate=agora + timedelta(days=5),
        )
        self.assertEqual(self.nomes()[0], "Pago mais tarde")

    def test_plano_pago_vencido_nao_conta(self):
        from ..constants import PlanoDestaque

        agora = timezone.now()
        criar_evento(nome="Comum mais cedo", data=agora + timedelta(days=1))
        criar_evento(
            nome="Pago vencido",
            data=agora + timedelta(days=10),
            plano_destaque=PlanoDestaque.PREMIUM,
            destaque_pago_ate=agora - timedelta(days=1),
        )
        self.assertEqual(self.nomes(), ["Comum mais cedo", "Pago vencido"])


class DestaquesTests(TestCase):
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


@override_settings(CACHE_PAGINA_ATIVO=True)
class CachePaginaTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_visitante_anonimo_recebe_a_pagina_cacheada(self):
        criar_evento(nome="Evento Cacheado Um")
        primeira = self.client.get(reverse("lista_eventos"))
        self.assertIn(b"Evento Cacheado Um", primeira.content)

        # sem nenhuma mudança no catálogo, a segunda requisição é servida do
        # cache — nem toca o banco.
        with self.assertNumQueries(0):
            segunda = self.client.get(reverse("lista_eventos"))
        self.assertEqual(segunda.content, primeira.content)

    def test_criar_evento_invalida_o_cache_na_hora(self):
        criar_evento(nome="Evento Cacheado Um")
        primeira = self.client.get(reverse("lista_eventos"))
        self.assertIn(b"Evento Cacheado Um", primeira.content)

        criar_evento(nome="Evento Cacheado Dois")
        segunda = self.client.get(reverse("lista_eventos"))
        # o sinal em signals.py limpa o cache de páginas ao salvar um evento,
        # então o visitante anônimo vê o evento novo na mesma hora, sem
        # esperar os 180s de TTL.
        self.assertIn(b"Evento Cacheado Dois", segunda.content)

    def test_usuario_logado_nunca_ve_versao_cacheada(self):
        self.client.force_login(criar_usuario("logado-cache@exemplo.test"))

        criar_evento(nome="Evento Logado Um")
        primeira = self.client.get(reverse("lista_eventos"))
        self.assertIn(b"Evento Logado Um", primeira.content)

        criar_evento(nome="Evento Logado Dois")
        segunda = self.client.get(reverse("lista_eventos"))
        self.assertIn(b"Evento Logado Dois", segunda.content)

    def test_visitante_que_so_ve_pagina_cacheada_ganha_cookie_csrf_proprio(self):
        # O primeiro visitante popula o cache; a view (e o {% csrf_token %} do
        # formulário do assistente) roda de verdade só pra ele. Um segundo
        # visitante, que nunca teve o cookie CSRF antes, precisa sair da
        # página cacheada com o próprio cookie — senão qualquer POST dele
        # (como a pergunta ao assistente) cai em 403 CSRF.
        cliente_um = Client(enforce_csrf_checks=True)
        cliente_um.get(reverse("home"))

        cliente_dois = Client(enforce_csrf_checks=True)
        resposta = cliente_dois.get(reverse("home"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, cliente_dois.cookies)


class ServiceWorkerTests(TestCase):
    # `{% static '' %}` funciona em dev (StaticFilesStorage só concatena
    # STATIC_URL), mas quebra com o storage com manifesto que a produção usa
    # (whitenoise.storage.CompressedManifestStaticFilesStorage): uma entrada
    # vazia nunca existe no manifesto, e o lookup levanta ValueError. Simula
    # o storage de produção pra pegar essa classe de erro.
    def test_sw_js_renderiza_com_storage_de_manifesto(self):
        raiz_estatica = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, raiz_estatica, ignore_errors=True)

        with override_settings(
            STATIC_ROOT=raiz_estatica,
            STORAGES={
                **settings.STORAGES,
                "staticfiles": {
                    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                },
            },
        ):
            call_command("collectstatic", interactive=False, verbosity=0)
            resposta = self.client.get(reverse("service_worker"))

        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'"/static/"', resposta.content)
