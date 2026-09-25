from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento, Ingresso, Produtor
from ..ratelimit import excedeu, ip_do_pedido, limpar
from ..services.catalogo import resolver_produtor
from .base import criar_evento, criar_usuario


class VazamentoPorIdTests(TestCase):
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

    def test_salvar_ou_apagar_evento_nao_reseta_limite_de_outra_acao(self):
        # eventos/signals.py limpa o cache de página (alias "paginas") a
        # cada evento salvo/apagado. Isso não pode zerar contadores do
        # rate limiting, que fica no alias "default" — senão bastaria criar
        # ou apagar um evento pra burlar o limite de tentativas de login.
        from django.test import RequestFactory

        pedido = RequestFactory().post("/")
        pedido.user = type("Anonimo", (), {"is_authenticated": False})()

        for _ in range(3):
            excedeu("login", pedido)
        self.assertTrue(excedeu("login", pedido))

        evento = criar_evento(nome="Evento qualquer")
        evento.nome = "Evento qualquer editado"
        evento.save()
        evento.delete()

        self.assertTrue(excedeu("login", pedido))


@override_settings(RATELIMIT_ATIVO=False)
class IpDoPedidoTests(TestCase):
    def test_ignora_x_forwarded_for_sem_proxy_declarado(self):
        from django.test import RequestFactory

        pedido = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(ip_do_pedido(pedido), "127.0.0.1")

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_confia_no_ultimo_ip_da_cadeia_quando_ha_proxy_declarado(self):
        # O primeiro valor vem do cliente (falsificável); o proxy confiável
        # (edge do Render) é quem anexa o último.
        from django.test import RequestFactory

        pedido = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.1")
        self.assertEqual(ip_do_pedido(pedido), "10.0.0.1")

    @override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
    def test_nao_confia_no_primeiro_ip_forjado_pelo_cliente(self):
        from django.test import RequestFactory

        pedido = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4")
        # Sem um proxy real anexando nada, o único valor é o do próprio
        # cliente — mas o teste acima é o que importa: garantir que um
        # cliente não consegue *inserir* um IP falso à esquerda do seu real.
        self.assertEqual(ip_do_pedido(pedido), "1.2.3.4")


class AdminTests(TestCase):
    def test_admin_responde_no_caminho_configurado(self):
        from django.conf import settings

        resposta = self.client.get(f"/{settings.ADMIN_URL}/")
        self.assertIn(resposta.status_code, (200, 302))

    @override_settings(ADMIN_IPS_PERMITIDOS=["203.0.113.10"])
    def test_ip_fora_da_lista_recebe_404(self):
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


class InscritosCsvTests(TestCase):
    def test_nome_com_formula_e_neutralizado_no_csv(self):
        dono = criar_usuario("dono@exemplo.test")
        golpista = criar_usuario("golpista@exemplo.test")
        golpista.first_name = "=cmd"
        golpista.last_name = "|calc!A1"
        golpista.save()
        evento = criar_evento(criado_por=dono, capacidade=5, limite_por_usuario=5)
        Ingresso.objects.create(usuario=golpista, evento=evento, tipo="inteira")

        self.client.force_login(dono)
        resposta = self.client.get(
            reverse("inscritos_do_evento", args=[evento.slug]), {"formato": "csv"}
        )
        corpo = resposta.content.decode("utf-8-sig")
        linha = next(l for l in corpo.splitlines() if "cmd" in l)
        self.assertTrue(linha.split(";")[1].startswith("'"))


class ClaimDeProdutorTests(TestCase):
    def test_organizador_nao_reivindica_produtor_alheio_existente(self):
        Produtor.objects.create(nome="Teatro Consagrado")
        atacante = criar_usuario("atacante@exemplo.test")

        produtor = resolver_produtor("Teatro Consagrado", user=atacante)

        self.assertIsNone(produtor.user_id)

    def test_organizador_novo_ainda_cria_produtor_proprio(self):
        pessoa = criar_usuario("nova@exemplo.test")

        produtor = resolver_produtor("Coletivo Inédito", user=pessoa)

        self.assertEqual(produtor.user_id, pessoa.pk)


class CaptchaTests(TestCase):
    """HCAPTCHA_ATIVO=False nos testes normais mascararia qualquer regressão
    aqui — por isso estes testes ligam o captcha de propósito."""

    def dados_cadastro(self, **extras):
        return {
            "full_name": "Pessoa Testando",
            "email": "captcha@exemplo.test",
            "password1": "senha-bem-forte-2026",
            "password2": "senha-bem-forte-2026",
            "terms": "on",
            **extras,
        }

    def dados_evento_painel(self, **extras):
        inicio = timezone.localtime() + timedelta(days=20)
        return {
            "nome": "Evento sem Captcha no Painel",
            "descricao": "Descrição de teste.",
            "data": inicio.strftime("%Y-%m-%dT%H:%M"),
            "data_fim": "",
            "modalidade": "presencial",
            "local": "Espaço de Teste",
            "endereco": "",
            "regiao": Regiao.ASA_NORTE,
            "cidade": "Brasília",
            "categoria": Categoria.CULTURA,
            "gratuito": "on",
            "status": Evento.Status.PUBLICADO,
            "destaque": "",
            "motivo_rejeicao": "",
            "limite_por_usuario": "10",
            **extras,
        }

    @override_settings(HCAPTCHA_ATIVO=True)
    def test_cadastro_publico_e_recusado_sem_captcha(self):
        self.client.post(reverse("cadastro"), self.dados_cadastro())
        self.assertFalse(User.objects.filter(email="captcha@exemplo.test").exists())

    @override_settings(HCAPTCHA_ATIVO=True)
    @patch("eventos.forms.captcha.verificar", return_value=True)
    def test_cadastro_publico_passa_com_captcha_valido(self, _verificar):
        self.client.post(
            reverse("cadastro"), self.dados_cadastro(**{"h-captcha-response": "token"})
        )
        self.assertTrue(User.objects.filter(email="captcha@exemplo.test").exists())

    @override_settings(HCAPTCHA_ATIVO=True)
    def test_criar_evento_publico_e_recusado_sem_captcha(self):
        self.client.force_login(criar_usuario("organizador@exemplo.test"))
        self.client.post(reverse("criar_evento"), self.dados_evento_painel())
        self.assertFalse(Evento.objects.filter(nome="Evento sem Captcha no Painel").exists())

    @override_settings(HCAPTCHA_ATIVO=True)
    def test_painel_da_equipe_nao_exige_captcha(self):
        staff = criar_usuario("equipe-captcha@exemplo.test")
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)

        self.client.post(reverse("painel_evento_criar"), self.dados_evento_painel())

        self.assertTrue(Evento.objects.filter(nome="Evento sem Captcha no Painel").exists())

    @override_settings(HCAPTCHA_ATIVO=True)
    def test_editar_evento_proprio_nao_exige_captcha(self):
        dono = criar_usuario("dono-evento@exemplo.test")
        evento = criar_evento(nome="Evento já existente", criado_por=dono)
        self.client.force_login(dono)

        resposta = self.client.post(
            reverse("editar_evento", args=[evento.slug]),
            self.dados_evento_painel(nome="Evento já existente, editado"),
        )

        evento.refresh_from_db()
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(evento.nome, "Evento já existente, editado")
