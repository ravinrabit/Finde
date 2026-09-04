"""Rate limiting, admin endurecido e vazamento de eventos não publicados."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import Evento
from ..ratelimit import excedeu, ip_do_pedido, limpar
from .base import criar_evento, criar_usuario


class VazamentoPorIdTests(TestCase):
    """BUG 7 — /evento/<id>/ redirecionava 301 mesmo para evento não publicado.

    Enumerar ids devolvia o slug — ou seja, o nome — de eventos pendentes e
    rejeitados, que ainda não deveriam existir para o público.
    """

    def setUp(self):
        self.publicado = criar_evento(nome="Show público")
        self.pendente = criar_evento(nome="Segredo ainda não aprovado", status=Evento.Status.PENDENTE)
        self.rejeitado = criar_evento(nome="Recusado pela moderação", status=Evento.Status.REJEITADO)

    def test_publicado_redireciona_para_o_slug(self):
        resposta = self.client.get(reverse("evento_por_id", args=[self.publicado.pk]))
        self.assertEqual(resposta.status_code, 301)

    def test_pendente_devolve_404_em_vez_de_redirecionar(self):
        resposta = self.client.get(reverse("evento_por_id", args=[self.pendente.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_rejeitado_devolve_404(self):
        resposta = self.client.get(reverse("evento_por_id", args=[self.rejeitado.pk]))
        self.assertEqual(resposta.status_code, 404)

    def test_o_slug_do_pendente_nao_vaza_no_cabecalho(self):
        resposta = self.client.get(reverse("evento_por_id", args=[self.pendente.pk]))
        self.assertNotIn("Location", resposta.headers)


@override_settings(
    RATELIMIT_ATIVO=True,
    RATELIMITS={"login": (3, 900), "cadastro": (2, 3600), "busca": (5, 60)},
)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_bloqueia_depois_do_limite(self):
        dados = {"username": "ninguem@exemplo.test", "password": "errada"}
        for _ in range(3):
            self.client.post(reverse("login"), dados)
        resposta = self.client.post(reverse("login"), dados)
        self.assertEqual(resposta.status_code, 429)

    def test_resposta_429_traz_retry_after(self):
        dados = {"username": "ninguem@exemplo.test", "password": "errada"}
        for _ in range(4):
            resposta = self.client.post(reverse("login"), dados)
        self.assertIn("Retry-After", resposta.headers)

    def test_get_no_login_nao_conta(self):
        for _ in range(10):
            resposta = self.client.get(reverse("login"))
        self.assertEqual(resposta.status_code, 200)

    def test_cadastro_bloqueia_criacao_em_massa(self):
        for indice in range(2):
            self.client.post(
                reverse("cadastro"),
                {
                    "full_name": f"Pessoa {indice}",
                    "email": f"massa{indice}@exemplo.test",
                    "password1": "senha-bem-forte-2026",
                    "password2": "senha-bem-forte-2026",
                    "terms": "on",
                },
            )
        resposta = self.client.post(
            reverse("cadastro"),
            {
                "full_name": "Pessoa 3",
                "email": "massa3@exemplo.test",
                "password1": "senha-bem-forte-2026",
                "password2": "senha-bem-forte-2026",
                "terms": "on",
            },
        )
        self.assertEqual(resposta.status_code, 429)
        self.assertFalse(User.objects.filter(email="massa3@exemplo.test").exists())

    def test_contador_pode_ser_zerado(self):
        # Direto na API, sem passar por view.
        from django.test import RequestFactory

        pedido = RequestFactory().post("/")
        pedido.user = type("Anonimo", (), {"is_authenticated": False})()

        for _ in range(3):
            excedeu("login", pedido)
        self.assertTrue(excedeu("login", pedido))
        limpar("login", pedido)
        self.assertFalse(excedeu("login", pedido))


@override_settings(RATELIMIT_ATIVO=False)
class IpDoPedidoTests(TestCase):
    def test_ignora_x_forwarded_for_sem_proxy_declarado(self):
        """Sem SECURE_PROXY_SSL_HEADER, o cabeçalho é forjável — confiar nele
        faria qualquer limite virar decoração."""
        from django.test import RequestFactory

        pedido = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(ip_do_pedido(pedido), "127.0.0.1")

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_confia_no_cabecalho_quando_ha_proxy_declarado(self):
        from django.test import RequestFactory

        pedido = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1")
        self.assertEqual(ip_do_pedido(pedido), "1.2.3.4")


class AdminTests(TestCase):
    def test_admin_responde_no_caminho_configurado(self):
        from django.conf import settings

        resposta = self.client.get(f"/{settings.ADMIN_URL}/")
        self.assertIn(resposta.status_code, (200, 302))

    @override_settings(ADMIN_IPS_PERMITIDOS=["203.0.113.10"])
    def test_ip_fora_da_lista_recebe_404(self):
        """404, e não 403: negar a existência entrega menos informação."""
        from django.conf import settings
        from django.test import Client

        # O middleware lê a allowlist na inicialização, então é preciso
        # reconstruir a pilha de middleware para o override valer.
        from django.core.handlers.base import BaseHandler

        cliente = Client()
        BaseHandler.load_middleware(cliente.handler)
        resposta = cliente.get(f"/{settings.ADMIN_URL}/")
        self.assertEqual(resposta.status_code, 404)


class SaudeTests(TestCase):
    def test_health_check_simples_responde(self):
        resposta = self.client.get(reverse("health_check"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "ok")

    def test_detalhado_sem_token_e_invisivel(self):
        self.assertEqual(self.client.get(reverse("health_check_detalhado")).status_code, 404)

    @override_settings(HEALTHCHECK_TOKEN="segredo-de-teste")
    def test_detalhado_com_token_verifica_os_servicos(self):
        resposta = self.client.get(reverse("health_check_detalhado"), {"token": "segredo-de-teste"})
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["banco"], "ok")
        self.assertEqual(dados["cache"], "ok")

    @override_settings(HEALTHCHECK_TOKEN="segredo-de-teste")
    def test_detalhado_com_token_errado_e_invisivel(self):
        resposta = self.client.get(reverse("health_check_detalhado"), {"token": "chute"})
        self.assertEqual(resposta.status_code, 404)


class VisualizacaoTests(TestCase):
    """BUG 10 — registrar_visualizacao() era um UPDATE em todo GET, sem dedupe.

    O número inflava com Googlebot, monitoramento e F5, e o site escrevia no
    banco a cada visita de leitura.
    """

    def test_recarregar_nao_conta_de_novo(self):
        evento = criar_evento()
        url = evento.get_absolute_url()
        for _ in range(5):
            self.client.get(url)
        evento.refresh_from_db()
        self.assertEqual(evento.visualizacoes, 1)

    def test_sessao_nova_conta_de_novo(self):
        from django.test import Client

        evento = criar_evento()
        self.client.get(evento.get_absolute_url())
        Client().get(evento.get_absolute_url())
        evento.refresh_from_db()
        self.assertEqual(evento.visualizacoes, 2)
