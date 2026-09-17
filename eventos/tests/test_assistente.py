import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ..services import assistente


class AssistenteIndisponivelTests(TestCase):
    def test_responder_levanta_quando_desligado(self):
        with self.assertRaises(assistente.AssistenteIndisponivel):
            assistente.responder("quais shows tem essa semana?")


class AssistentePerguntarViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_nao_e_permitido(self):
        resposta = self.client.get(reverse("assistente_perguntar"))
        self.assertEqual(resposta.status_code, 405)

    def test_pergunta_vazia_e_recusada(self):
        resposta = self.client.post(
            reverse("assistente_perguntar"),
            data=json.dumps({"pergunta": ""}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_assistente_desligado_responde_503(self):
        resposta = self.client.post(
            reverse("assistente_perguntar"),
            data=json.dumps({"pergunta": "o que tem para fazer hoje?"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 503)

    @override_settings(RATELIMIT_ATIVO=True, RATELIMITS={"assistente": (1, 60)})
    def test_respeita_o_limite_de_taxa(self):
        corpo = json.dumps({"pergunta": "oi"})
        self.client.post(reverse("assistente_perguntar"), data=corpo, content_type="application/json")
        resposta = self.client.post(
            reverse("assistente_perguntar"), data=corpo, content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 429)
