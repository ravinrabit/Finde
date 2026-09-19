from unittest.mock import MagicMock

from django.test import SimpleTestCase

from ..templatetags.finde import capa


def evento_falso(imagem_exibicao="", imagem=None, banner=None, nome="Evento"):
    evento = MagicMock()
    evento.nome = nome
    evento.imagem_exibicao = imagem_exibicao
    evento.imagem = imagem
    evento.banner = banner
    return evento


class CapaTemplateTagTests(SimpleTestCase):
    def test_sem_preferir_banner_usa_a_imagem_normal(self):
        banner = MagicMock(url="https://exemplo.test/banner.jpg")
        evento = evento_falso(imagem_exibicao="https://exemplo.test/capa.jpg", banner=banner)
        html = capa(evento)
        self.assertIn("capa.jpg", html)
        self.assertNotIn("banner.jpg", html)

    def test_preferir_banner_usa_o_banner_quando_presente(self):
        banner = MagicMock(url="https://exemplo.test/banner.jpg")
        evento = evento_falso(imagem_exibicao="https://exemplo.test/capa.jpg", banner=banner)
        html = capa(evento, preferir_banner=True)
        self.assertIn("banner.jpg", html)

    def test_preferir_banner_cai_na_imagem_normal_sem_banner(self):
        evento = evento_falso(imagem_exibicao="https://exemplo.test/capa.jpg", banner=None)
        html = capa(evento, preferir_banner=True)
        self.assertIn("capa.jpg", html)

    def test_sem_nenhuma_imagem_retorna_vazio(self):
        evento = evento_falso(imagem_exibicao="", banner=None)
        self.assertEqual(capa(evento, preferir_banner=True), "")
