"""Ingestão: fuso, status de curadoria, idempotência e conectores.

BUG 9 — o importador gerava datetime sem fuso com USE_TZ=True (erro de 3 h) e
gravava tudo como PUBLICADO, direto no ar, sem ninguém olhar.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..ingestao import salvar_importados
from ..ingestao.base import EventoImportado, garantir_aware
from ..ingestao import ics, jsonld
from ..models import Evento, Local, Produtor


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


class PoliticaDeCuradoriaTests(TestCase):
    def test_importado_entra_como_pendente(self):
        salvar_importados([importado()], fonte="mapa-df")
        self.assertEqual(Evento.objects.get().status, Evento.Status.PENDENTE)

    def test_evento_pendente_nao_aparece_no_site(self):
        salvar_importados([importado()], fonte="mapa-df")
        self.assertEqual(Evento.objects.visiveis().count(), 0)

    def test_fonte_de_confianca_pode_publicar_explicitamente(self):
        salvar_importados([importado()], fonte="parceiros", status=Evento.Status.PUBLICADO)
        self.assertEqual(Evento.objects.get().status, Evento.Status.PUBLICADO)

    def test_reimportacao_nao_republica_o_que_foi_rejeitado(self):
        salvar_importados([importado()], fonte="mapa-df")
        evento = Evento.objects.get()
        evento.status = Evento.Status.REJEITADO
        evento.save()

        salvar_importados([importado(nome="Nome novo")], fonte="mapa-df")
        evento.refresh_from_db()
        self.assertEqual(evento.status, Evento.Status.REJEITADO)
        self.assertEqual(evento.nome, "Nome novo")


class VinculoDeEntidadesTests(TestCase):
    def test_local_e_criado_a_partir_do_texto(self):
        salvar_importados([importado()], fonte="mapa-df")
        self.assertEqual(Local.objects.count(), 1)
        self.assertEqual(Evento.objects.get().local_ref.nome, "Arena de Taguatinga")

    def test_locais_com_grafia_diferente_viram_um_so(self):
        salvar_importados([importado(id_externo="1", local="Cine Brasília")], fonte="t")
        salvar_importados([importado(id_externo="2", local="cine brasilia")], fonte="t")
        self.assertEqual(Local.objects.count(), 1)

    def test_produtor_e_criado_a_partir_do_organizador(self):
        salvar_importados([importado(organizador="Coletivo Cerrado")], fonte="t")
        self.assertEqual(Produtor.objects.get().nome, "Coletivo Cerrado")

    def test_coordenada_da_fonte_e_aproveitada(self):
        salvar_importados(
            [importado(latitude=-15.8333, longitude=-48.0578)], fonte="mapa-df"
        )
        local = Local.objects.get()
        self.assertIsNotNone(local.latitude)
        self.assertEqual(Evento.objects.get().latitude, local.latitude)

    def test_local_existente_recebe_dados_que_faltavam(self):
        Local.objects.create(nome="Arena de Taguatinga")
        salvar_importados([importado(endereco="QNL 10, Taguatinga")], fonte="t")
        self.assertEqual(Local.objects.get().endereco, "QNL 10, Taguatinga")


class CamposDerivadosTests(TestCase):
    """save(update_fields=...) não pode descartar o que o próprio save deriva.

    Desde o Django 4.2, update_or_create() chama save(update_fields=<chaves de
    defaults>). Coordenada herdada do local e região inferida eram calculadas
    em memória e nunca chegavam ao banco: um evento reimportado ficava sem
    coordenada e sem região para sempre.
    """

    def test_regiao_vazia_e_preenchida_na_reimportacao(self):
        salvar_importados([importado(local="Galpão sem referência")], fonte="t")
        self.assertEqual(Evento.objects.get().regiao, "")

        salvar_importados([importado(local="Arena de Taguatinga")], fonte="t")
        self.assertEqual(Evento.objects.get().regiao, Regiao.TAGUATINGA)

    def test_coordenada_chega_ao_banco_na_reimportacao(self):
        salvar_importados([importado()], fonte="t")
        self.assertIsNone(Evento.objects.get().latitude)

        salvar_importados(
            [importado(latitude=-15.8333, longitude=-48.0578)], fonte="t"
        )
        evento = Evento.objects.get()
        self.assertIsNotNone(evento.latitude, "a coordenada foi perdida por update_fields")
        self.assertEqual(evento.latitude, evento.local_ref.latitude)

    def test_busca_texto_acompanha_a_atualizacao(self):
        salvar_importados([importado(nome="Nome antigo")], fonte="t")
        salvar_importados([importado(nome="Sarau na Ceilândia")], fonte="t")
        self.assertIn("sarau", Evento.objects.get().busca_texto)
        self.assertNotIn("antigo", Evento.objects.get().busca_texto)


class CategoriaAcentuadaTests(TestCase):
    """BUG 6 — Categoria.UNIVERSITARIO valia "universitário", com acento.

    slugify() nunca produz acento, então a comparação jamais casava e nenhum
    evento importado entrava nessa categoria.
    """

    def test_valor_da_categoria_e_ascii(self):
        self.assertEqual(Categoria.UNIVERSITARIO.value, "universitario")

    def test_categoria_universitaria_agora_e_atribuida(self):
        salvar_importados([importado(categoria="Universitário")], fonte="t")
        self.assertEqual(Evento.objects.get().categoria, Categoria.UNIVERSITARIO)


class InferenciaDeRegiaoTests(TestCase):
    def test_regiao_inferida_pelo_nome_do_local(self):
        salvar_importados([importado(local="Arena de Taguatinga")], fonte="t")
        self.assertEqual(Evento.objects.get().regiao, Regiao.TAGUATINGA)

    def test_rotulo_curto_nao_casa_dentro_de_outra_palavra(self):
        """"gama" não pode casar em "Gamarra": rótulos curtos exigem palavra inteira."""
        salvar_importados([importado(local="Bar do Gamarra")], fonte="t")
        self.assertNotEqual(Evento.objects.get().regiao, Regiao.GAMA)

    def test_rotulo_curto_casa_como_palavra_inteira(self):
        salvar_importados([importado(local="Estádio do Gama")], fonte="t")
        self.assertEqual(Evento.objects.get().regiao, Regiao.GAMA)


class ValidacaoTests(TestCase):
    def test_evento_sem_nome_e_descartado(self):
        resultado = salvar_importados([importado(nome="")], fonte="t")
        self.assertEqual(resultado["ignorados"], 1)

    def test_evento_sem_id_externo_e_descartado(self):
        resultado = salvar_importados([importado(id_externo="")], fonte="t")
        self.assertEqual(resultado["ignorados"], 1)

    def test_data_fim_antes_do_inicio_e_descartada_com_aviso(self):
        item = importado(data_fim=timezone.now() + timedelta(days=1))
        resultado = salvar_importados([item], fonte="t")
        self.assertEqual(resultado["criados"], 1)
        self.assertIsNone(Evento.objects.get().data_fim)
        self.assertTrue(resultado["avisos"])

    def test_mesma_id_em_fontes_diferentes_gera_dois_eventos(self):
        salvar_importados([importado()], fonte="mapa-df")
        salvar_importados([importado()], fonte="parceiros")
        self.assertEqual(Evento.objects.count(), 2)


class LeitorIcsTests(TestCase):
    FEED = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:evento-1@exemplo.test\r\n"
        "DTSTART:20301225T210000Z\r\n"
        "DTEND:20301225T230000Z\r\n"
        "SUMMARY:Natal no Cerrado\r\n"
        "LOCATION:Praça do Relógio\\, Taguatinga\r\n"
        "DESCRIPTION:Uma linha bem longa que o formato dobra em 75 octetos e p\r\n"
        " recisa ser remontada pelo leitor.\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    def test_le_um_evento_do_feed(self):
        achados = ics.eventos_do_feed(self.FEED, "https://exemplo.test/agenda.ics", "teste")
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0].nome, "Natal no Cerrado")

    def test_desescapa_virgula(self):
        achado = ics.eventos_do_feed(self.FEED, "u", "t")[0]
        self.assertEqual(achado.local, "Praça do Relógio, Taguatinga")

    def test_remonta_linha_dobrada(self):
        achado = ics.eventos_do_feed(self.FEED, "u", "t")[0]
        self.assertIn("precisa ser remontada", achado.descricao)

    def test_data_em_utc_e_convertida(self):
        achado = ics.eventos_do_feed(self.FEED, "u", "t")[0]
        self.assertIsNotNone(achado.data.tzinfo)
        self.assertEqual(timezone.localtime(achado.data).hour, 18)  # 21h UTC = 18h em Brasília


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
