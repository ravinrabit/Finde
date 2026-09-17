from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from ..ingestao.base import EventoImportado, garantir_aware
from ..ingestao import jsonld


def importado(**extras):
    padrao = {
        "id_externo": "abc-123",
        "nome": "Show importado",
        "data": timezone.now() + timedelta(days=10),
        "local": "Arena de Taguatinga",
        "link_original": "https://exemplo.test/evento/abc-123",
    }
    return EventoImportado(**{**padrao, **extras})


class FusoHorarioTests(TestCase):
    def test_datetime_sem_fuso_e_ancorado_no_fuso_do_projeto(self):
        ingenuo = datetime(2026, 12, 25, 21, 0)
        com_fuso = garantir_aware(ingenuo)

        self.assertIsNotNone(com_fuso.tzinfo)
        # Anunciado às 21h em Brasília precisa continuar 21h no fuso local.
        self.assertEqual(timezone.localtime(com_fuso).hour, 21)

    def test_datetime_com_fuso_nao_e_alterado(self):
        original = timezone.now()
        self.assertEqual(garantir_aware(original), original)

    def test_none_continua_none(self):
        self.assertIsNone(garantir_aware(None))

    def test_importado_ancora_a_data_no_construtor(self):
        item = importado(data=datetime(2026, 12, 25, 21, 0))
        self.assertIsNotNone(item.data.tzinfo)


class SanitizacaoDeUrlTests(TestCase):
    def test_link_original_com_esquema_perigoso_e_descartado(self):
        item = importado(link_original="javascript:alert(1)")
        self.assertEqual(item.link_original, "")

    def test_link_original_http_e_mantido(self):
        item = importado(link_original="https://exemplo.test/evento")
        self.assertEqual(item.link_original, "https://exemplo.test/evento")

    def test_imagem_url_com_esquema_perigoso_e_descartada(self):
        item = importado(imagem_url="javascript:alert(1)")
        self.assertEqual(item.imagem_url, "")


class LeitorJsonLdTests(TestCase):
    HTML = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Event",
     "name":"Mostra de Cinema",
     "startDate":"2030-11-10T20:00:00-03:00",
     "endDate":"2030-11-10T22:30:00-03:00",
     "location":{"@type":"Place","name":"Cine Brasília",
                 "address":{"@type":"PostalAddress","streetAddress":"EQS 106/107","addressLocality":"Brasília"},
                 "geo":{"@type":"GeoCoordinates","latitude":-15.8267,"longitude":-47.9089}},
     "organizer":{"@type":"Organization","name":"Secretaria de Cultura"},
     "offers":[{"@type":"Offer","price":"0","priceCurrency":"BRL"}],
     "image":"https://exemplo.test/capa.jpg"}
    </script>
    </head><body></body></html>
    """

    def bloco(self):
        return jsonld.extrair_blocos(self.HTML)[0]

    def test_encontra_o_bloco_de_evento(self):
        self.assertEqual(len(jsonld.extrair_blocos(self.HTML)), 1)

    def test_converte_para_evento_importado(self):
        item = jsonld.para_importado(self.bloco(), "https://exemplo.test/evento")
        self.assertEqual(item.nome, "Mostra de Cinema")
        self.assertEqual(item.local, "Cine Brasília")
        self.assertEqual(item.organizador, "Secretaria de Cultura")

    def test_preco_zero_vira_gratuito(self):
        item = jsonld.para_importado(self.bloco(), "u")
        self.assertTrue(item.gratuito)
        self.assertIsNone(item.preco)

    def test_coordenadas_sao_lidas(self):
        item = jsonld.para_importado(self.bloco(), "u")
        self.assertAlmostEqual(item.latitude, -15.8267, places=4)

    def test_graph_e_achatado(self):
        html = """<script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"WebSite","name":"Site"},
          {"@type":"MusicEvent","name":"Show","startDate":"2030-01-01T20:00:00"}]}
        </script>"""
        blocos = jsonld.extrair_blocos(html)
        self.assertEqual(len(blocos), 1)
        self.assertEqual(blocos[0]["name"], "Show")

    def test_json_malformado_nao_derruba(self):
        self.assertEqual(jsonld.extrair_blocos('<script type="application/ld+json">{{{</script>'), [])

    def test_evento_sem_data_e_descartado(self):
        self.assertIsNone(jsonld.para_importado({"@type": "Event", "name": "Sem data"}, "u"))
