"""Coordenadas, distância, raio e mapa — a base da descoberta hiperlocal."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from ..constants import Regiao
from ..models import Evento, Local, distancia_km
from ..services import geocoding
from .base import criar_evento, criar_local


class DistanciaTests(TestCase):
    def test_mesma_coordenada_da_zero(self):
        self.assertAlmostEqual(distancia_km(-15.79, -47.88, -15.79, -47.88), 0, places=6)

    def test_distancia_conhecida_no_df(self):
        """Congresso Nacional -> Praça do Relógio, em Taguatinga: ~19 km."""
        km = distancia_km(-15.7997, -47.8645, -15.8283, -48.0553)
        self.assertGreater(km, 17)
        self.assertLess(km, 22)

    def test_coordenada_faltando_devolve_none(self):
        self.assertIsNone(distancia_km(None, -47.88, -15.79, -47.88))


class LocalTests(TestCase):
    def test_slug_gerado_a_partir_do_nome(self):
        local = criar_local(nome="Cine Brasília")
        self.assertEqual(local.slug, "cine-brasilia")

    def test_nome_normalizado_permite_deduplicar(self):
        local = criar_local(nome="  Cine   BRASÍLIA ")
        self.assertEqual(local.nome_normalizado, "cine brasilia")

    def test_metro_proximo_e_calculado(self):
        # Coordenada da estação Praça do Relógio.
        local = criar_local(
            nome="Shopping JK",
            latitude=Decimal("-15.828300"),
            longitude=Decimal("-48.055300"),
            regiao=Regiao.TAGUATINGA,
        )
        self.assertTrue(local.atualizar_metro())
        self.assertEqual(local.metro_proximo, "Praça do Relógio")
        self.assertLess(local.metro_distancia_m, 200)

    def test_local_sem_coordenada_nao_tem_metro(self):
        local = criar_local(nome="Local sem coordenada", latitude=None, longitude=None)
        self.assertFalse(local.atualizar_metro())
        self.assertEqual(local.metro_proximo, "")

    def test_fila_de_geocodificacao_ignora_online(self):
        criar_local(nome="Evento online", latitude=None, longitude=None, regiao=Regiao.ONLINE)
        criar_local(nome="Espaço físico", latitude=None, longitude=None, regiao=Regiao.GAMA)
        pendentes = [l.nome for l in Local.objects.pendentes_de_geocodificacao()]
        self.assertEqual(pendentes, ["Espaço físico"])

    def test_fallback_usa_o_centro_da_regiao(self):
        """Sem rede, o local recebe o centroide da RA e fica marcado como aproximado —
        melhor um ponto aproximado do que um local invisível no mapa."""
        local = criar_local(nome="Casa nova", latitude=None, longitude=None, regiao=Regiao.CEILANDIA)
        resultado = geocoding.geocodificar_local(local, usar_rede=False)
        local.refresh_from_db()
        self.assertEqual(resultado, "aproximada")
        self.assertTrue(local.coordenada_aproximada)
        self.assertIsNotNone(local.latitude)

    def test_coordenada_fora_do_df_e_rejeitada(self):
        self.assertFalse(geocoding.dentro_do_df(-23.55, -46.63))  # São Paulo
        self.assertTrue(geocoding.dentro_do_df(-15.79, -47.88))


class VinculoAutomaticoDeLocalTests(TestCase):
    """Todo caminho de criação precisa gerar o Local, não só a ingestão.

    Enquanto só `salvar_importados()` e o formulário do produtor criavam
    Local, evento nascido do admin, do shell ou do semear_demo ficava sem
    coordenada — invisível em /mapa/ e no "perto de mim", com o catálogo
    cheio. O sintoma foi um mapa vazio em banco recém-populado.
    """

    def test_evento_criado_direto_ganha_local(self):
        evento = criar_evento(local="Clube do Choro")
        self.assertIsNotNone(evento.local_ref)
        self.assertEqual(evento.local_ref.nome, "Clube do Choro")

    def test_o_vinculo_sobrevive_ao_banco(self):
        pk = criar_evento(local="Cine Brasília").pk
        self.assertIsNotNone(Evento.objects.get(pk=pk).local_ref_id)

    def test_grafias_diferentes_compartilham_o_mesmo_local(self):
        criar_evento(nome="Sessão 1", local="Cine Brasília")
        criar_evento(nome="Sessão 2", local="cine brasilia")
        self.assertEqual(Local.objects.count(), 1)

    def test_evento_online_nao_cria_local(self):
        criar_evento(nome="Aula online", local="Transmissão online",
                     modalidade="online", regiao=Regiao.ONLINE)
        self.assertEqual(Local.objects.count(), 0)

    def test_local_a_confirmar_nao_vira_marcador_no_mapa(self):
        criar_evento(nome="Sem sede ainda", local="A confirmar")
        self.assertEqual(Local.objects.count(), 0)

    def test_local_ja_informado_nao_e_substituido(self):
        local = criar_local(nome="Casa do Cantador")
        evento = criar_evento(local_ref=local, local="Outro nome qualquer")
        self.assertEqual(evento.local_ref_id, local.pk)

    def test_endereco_e_regiao_do_evento_alimentam_o_local_novo(self):
        criar_evento(local="Galpão do Guará", endereco="QE 23", regiao=Regiao.GUARA)
        local = Local.objects.get()
        self.assertEqual(local.endereco, "QE 23")
        self.assertEqual(local.regiao, Regiao.GUARA)


class EventoGeoTests(TestCase):
    def setUp(self):
        self.central = criar_local(
            nome="Teatro Nacional",
            latitude=Decimal("-15.793900"),
            longitude=Decimal("-47.882800"),
            regiao=Regiao.PLANO_PILOTO,
        )
        self.distante = criar_local(
            nome="Casa do Cantador",
            latitude=Decimal("-15.817500"),
            longitude=Decimal("-48.107500"),
            regiao=Regiao.CEILANDIA,
        )
        self.perto = criar_evento(nome="Perto", local_ref=self.central, local="Teatro Nacional")
        self.longe = criar_evento(nome="Longe", local_ref=self.distante, local="Casa do Cantador")

    def test_coordenada_do_local_e_copiada_para_o_evento(self):
        self.assertEqual(self.perto.latitude, self.central.latitude)

    def test_regiao_e_herdada_do_local(self):
        evento = criar_evento(nome="Sem região", local_ref=self.central, local="Teatro Nacional", regiao="")
        self.assertEqual(evento.regiao, Regiao.PLANO_PILOTO)

    def test_filtro_por_raio_recorta_o_conjunto(self):
        proximos = Evento.objects.no_raio(-15.7939, -47.8828, 5)
        nomes = [e.nome for e in proximos]
        self.assertIn("Perto", nomes)
        self.assertNotIn("Longe", nomes)

    def test_raio_grande_pega_os_dois(self):
        proximos = Evento.objects.no_raio(-15.7939, -47.8828, 40)
        self.assertEqual(proximos.count(), 2)

    def test_distancia_de_um_ponto(self):
        km = self.longe.distancia_de(-15.7939, -47.8828)
        self.assertGreater(km, 20)


class MapaTests(TestCase):
    def setUp(self):
        local = criar_local(nome="Parque da Cidade")
        criar_evento(nome="Evento com mapa", local_ref=local, local="Parque da Cidade")
        criar_evento(nome="Evento sem coordenada", local="Endereço solto")

    def test_pagina_do_mapa_responde(self):
        resposta = self.client.get(reverse("mapa_eventos"))
        self.assertEqual(resposta.status_code, 200)

    def test_geojson_traz_so_quem_tem_coordenada(self):
        resposta = self.client.get(reverse("mapa_dados"))
        dados = resposta.json()
        self.assertEqual(dados["type"], "FeatureCollection")
        nomes = [f["properties"]["nome"] for f in dados["features"]]
        self.assertEqual(nomes, ["Evento com mapa"])

    def test_geojson_usa_ordem_lon_lat(self):
        """GeoJSON exige [longitude, latitude], nessa ordem. Trocar inverte o mapa."""
        recurso = self.client.get(reverse("mapa_dados")).json()["features"][0]
        lon, lat = recurso["geometry"]["coordinates"]
        self.assertLess(lon, -40)
        self.assertLess(lat, -10)
        self.assertGreater(lat, -20)

    def test_geojson_respeita_os_filtros(self):
        resposta = self.client.get(reverse("mapa_dados"), {"q": "inexistente"})
        self.assertEqual(resposta.json()["features"], [])


class PertoDeMimTests(TestCase):
    def setUp(self):
        self.central = criar_local(
            nome="Clube do Choro",
            latitude=Decimal("-15.793900"),
            longitude=Decimal("-47.882800"),
        )
        self.distante = criar_local(
            nome="Arena do Gama",
            latitude=Decimal("-16.020800"),
            longitude=Decimal("-48.064400"),
            regiao=Regiao.GAMA,
        )
        criar_evento(nome="Choro no Plano", local_ref=self.central, local="Clube do Choro")
        criar_evento(nome="Jogo no Gama", local_ref=self.distante, local="Arena do Gama")

    def test_raio_filtra_a_listagem(self):
        resposta = self.client.get(
            reverse("lista_eventos"), {"lat": "-15.7939", "lon": "-47.8828", "raio": "5"}
        )
        nomes = [e.nome for e in resposta.context["eventos"]]
        self.assertEqual(nomes, ["Choro no Plano"])

    def test_raio_sem_coordenada_e_ignorado(self):
        resposta = self.client.get(reverse("lista_eventos"), {"raio": "1"})
        self.assertEqual(len(resposta.context["eventos"]), 2)

    def test_coordenada_absurda_e_ignorada(self):
        resposta = self.client.get(
            reverse("lista_eventos"), {"lat": "999", "lon": "999", "raio": "5"}
        )
        self.assertEqual(len(resposta.context["eventos"]), 2)

    def test_ordenar_por_distancia_coloca_o_mais_perto_primeiro(self):
        resposta = self.client.get(
            reverse("lista_eventos"),
            {"lat": "-16.0208", "lon": "-48.0644", "ordenar": "distancia"},
        )
        nomes = [e.nome for e in resposta.context["eventos"]]
        self.assertEqual(nomes[0], "Jogo no Gama")

    def test_distancia_e_anotada_nos_cards(self):
        resposta = self.client.get(
            reverse("lista_eventos"), {"lat": "-15.7939", "lon": "-47.8828", "ordenar": "distancia"}
        )
        primeiro = resposta.context["eventos"][0]
        self.assertIsNotNone(primeiro.distancia)


class PaginasDeLocalEProdutorTests(TestCase):
    def setUp(self):
        self.local = criar_local(nome="Cine Brasília")
        self.evento = criar_evento(local_ref=self.local, local="Cine Brasília")

    def test_pagina_do_local_lista_a_programacao(self):
        resposta = self.client.get(reverse("local_detalhe", args=[self.local.slug]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, self.evento.nome)

    def test_lista_de_locais_so_mostra_quem_tem_evento(self):
        criar_local(nome="Espaço vazio", slug="espaco-vazio")
        resposta = self.client.get(reverse("lista_locais"))
        nomes = [l.nome for l in resposta.context["pagina"]]
        self.assertIn("Cine Brasília", nomes)
        self.assertNotIn("Espaço vazio", nomes)

    def test_local_inexistente_devolve_404(self):
        self.assertEqual(self.client.get("/local/nao-existe/").status_code, 404)
