from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import DispositivoTOTP
from ..services import totp
from .base import criar_usuario


def _logar(client, email, senha):
    return client.post(reverse("login"), {"username": email, "password": senha})


class LoginSemStaffTests(TestCase):
    def test_login_normal_nao_passa_por_2fa(self):
        criar_usuario("comum@exemplo.test", "senha-forte-123")
        resposta = _logar(self.client, "comum@exemplo.test", "senha-forte-123")
        self.assertRedirects(resposta, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)


class ConfigurarDoisFatoresTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("staff@exemplo.test", "senha-forte-123")
        self.staff.is_staff = True
        self.staff.save()

    def test_login_de_staff_sem_dispositivo_vai_para_configuracao(self):
        resposta = _logar(self.client, "staff@exemplo.test", "senha-forte-123")
        self.assertRedirects(resposta, reverse("dois_fatores_configurar"))

    def test_staff_nao_fica_logado_antes_de_confirmar_o_codigo(self):
        _logar(self.client, "staff@exemplo.test", "senha-forte-123")
        self.assertNotIn("_auth_user_id", self.client.session)
        resposta = self.client.get(reverse("painel_evento_criar"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)

    def test_configurar_pagina_sem_login_pendente_manda_para_login(self):
        resposta = self.client.get(reverse("dois_fatores_configurar"))
        self.assertRedirects(resposta, reverse("login"))

    def test_codigo_errado_nao_confirma_dispositivo(self):
        _logar(self.client, "staff@exemplo.test", "senha-forte-123")
        resposta = self.client.post(reverse("dois_fatores_configurar"), {"codigo": "000000"})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DispositivoTOTP.objects.filter(usuario=self.staff, confirmado=True).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_codigo_certo_confirma_dispositivo_e_completa_o_login(self):
        _logar(self.client, "staff@exemplo.test", "senha-forte-123")
        self.client.get(reverse("dois_fatores_configurar"))  # é o GET que gera o segredo pendente
        segredo = self.client.session["2fa_segredo_pendente"]
        codigo = totp.codigo_atual(segredo)

        resposta = self.client.post(reverse("dois_fatores_configurar"), {"codigo": codigo})

        self.assertRedirects(resposta, reverse("home"))
        self.assertTrue(DispositivoTOTP.objects.get(usuario=self.staff).confirmado)
        self.assertIn("_auth_user_id", self.client.session)
        # e a sessão agora é de staff de verdade, painel acessível
        self.assertEqual(self.client.get(reverse("painel_evento_criar")).status_code, 200)


class VerificarDoisFatoresTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("staff2@exemplo.test", "senha-forte-123")
        self.staff.is_staff = True
        self.staff.save()
        self.segredo = totp.gerar_segredo()
        dispositivo = DispositivoTOTP.novo_para(self.staff, self.segredo)
        dispositivo.confirmado = True
        dispositivo.save(update_fields=["confirmado"])

    def _logar(self):
        return _logar(self.client, "staff2@exemplo.test", "senha-forte-123")

    def test_login_com_dispositivo_confirmado_pede_verificacao(self):
        resposta = self._logar()
        self.assertRedirects(resposta, reverse("dois_fatores_verificar"))

    def test_verificar_pagina_sem_login_pendente_manda_para_login(self):
        resposta = self.client.get(reverse("dois_fatores_verificar"))
        self.assertRedirects(resposta, reverse("login"))

    def test_codigo_errado_nao_loga(self):
        self._logar()
        resposta = self.client.post(reverse("dois_fatores_verificar"), {"codigo": "000000"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_codigo_certo_loga(self):
        self._logar()
        codigo = totp.codigo_atual(self.segredo)
        resposta = self.client.post(reverse("dois_fatores_verificar"), {"codigo": codigo})
        self.assertRedirects(resposta, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)

    @override_settings(RATELIMIT_ATIVO=True, RATELIMITS={"dois_fatores": (3, 900)})
    def test_tentativas_repetidas_sao_limitadas(self):
        self._logar()
        for _ in range(3):
            self.client.post(reverse("dois_fatores_verificar"), {"codigo": "000000"})
        resposta = self.client.post(reverse("dois_fatores_verificar"), {"codigo": "000000"})
        self.assertEqual(resposta.status_code, 429)
