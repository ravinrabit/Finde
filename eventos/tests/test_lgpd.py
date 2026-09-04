"""Direitos do titular: exportação, exclusão e registro de consentimento.

A política prometia acesso, portabilidade e exclusão, e apontava para uma
central de ajuda que não tinha canal nenhum. Estes testes garantem que a
promessa agora corresponde a código que roda.
"""

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..models import AceiteDeTermos, Evento, Favorito, Ingresso, Produtor
from ..services import lgpd
from .base import criar_evento, criar_usuario


class ConsentimentoTests(TestCase):
    def test_cadastro_registra_o_aceite(self):
        self.client.post(
            reverse("cadastro"),
            {
                "full_name": "Maria da Silva",
                "email": "maria@exemplo.test",
                "password1": "senha-bem-forte-2026",
                "password2": "senha-bem-forte-2026",
                "terms": "on",
            },
        )
        aceite = AceiteDeTermos.objects.get()
        self.assertEqual(aceite.usuario.email, "maria@exemplo.test")
        self.assertEqual(aceite.versao_termos, lgpd.VERSAO_TERMOS)

    def test_cadastro_sem_aceitar_termos_e_recusado(self):
        resposta = self.client.post(
            reverse("cadastro"),
            {
                "full_name": "Maria da Silva",
                "email": "maria2@exemplo.test",
                "password1": "senha-bem-forte-2026",
                "password2": "senha-bem-forte-2026",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(User.objects.filter(email="maria2@exemplo.test").exists())


class ExportacaoTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("titular@exemplo.test")
        self.evento = criar_evento(criado_por=self.pessoa)
        Ingresso.objects.create(usuario=self.pessoa, evento=self.evento)
        Favorito.objects.create(usuario=self.pessoa, evento=self.evento)
        self.client.force_login(self.pessoa)

    def test_exportacao_traz_tudo(self):
        dados = lgpd.exportar_dados(self.pessoa)
        self.assertEqual(dados["conta"]["email"], "titular@exemplo.test")
        self.assertEqual(len(dados["ingressos"]), 1)
        self.assertEqual(len(dados["favoritos"]), 1)
        self.assertEqual(len(dados["eventos_publicados"]), 1)

    def test_exportacao_nao_inclui_senha(self):
        bruto = json.dumps(lgpd.exportar_dados(self.pessoa))
        self.assertNotIn("password", bruto.lower())
        self.assertNotIn(self.pessoa.password, bruto)

    def test_view_devolve_json_para_download(self):
        resposta = self.client.get(reverse("exportar_meus_dados"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("application/json", resposta["Content-Type"])
        self.assertIn("attachment", resposta["Content-Disposition"])
        json.loads(resposta.content)

    def test_exportacao_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("exportar_meus_dados"))
        self.assertEqual(resposta.status_code, 302)


class ExclusaoTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("apagar@exemplo.test")
        self.evento = criar_evento(criado_por=self.pessoa, status=Evento.Status.PUBLICADO)
        Ingresso.objects.create(usuario=self.pessoa, evento=self.evento)
        Favorito.objects.create(usuario=self.pessoa, evento=self.evento)
        self.client.force_login(self.pessoa)

    def test_conta_e_apagada_de_verdade(self):
        lgpd.excluir_conta(self.pessoa)
        self.assertFalse(User.objects.filter(email="apagar@exemplo.test").exists())

    def test_ingressos_e_favoritos_somem(self):
        lgpd.excluir_conta(self.pessoa)
        self.assertEqual(Ingresso.objects.count(), 0)
        self.assertEqual(Favorito.objects.count(), 0)

    def test_eventos_publicados_ficam_sem_autor(self):
        """Apagar o evento derrubaria a agenda pública e prejudicaria terceiros."""
        lgpd.excluir_conta(self.pessoa)
        self.evento.refresh_from_db()
        self.assertIsNone(self.evento.criado_por)
        self.assertEqual(self.evento.status, Evento.Status.PUBLICADO)

    def test_produtor_e_desvinculado_mas_preservado(self):
        Produtor.objects.create(nome="Produtora da pessoa", user=self.pessoa)
        lgpd.excluir_conta(self.pessoa)
        produtor = Produtor.objects.get()
        self.assertIsNone(produtor.user_id)

    def test_view_exige_senha_correta(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"), {"senha": "errada", "confirmacao": "EXCLUIR"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.pessoa.pk).exists())

    def test_view_exige_a_palavra_de_confirmacao(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"), {"senha": "senha-forte-123", "confirmacao": "sim"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.pessoa.pk).exists())

    def test_view_apaga_com_senha_e_confirmacao(self):
        resposta = self.client.post(
            reverse("excluir_minha_conta"),
            {"senha": "senha-forte-123", "confirmacao": "EXCLUIR"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.pessoa.pk).exists())


class PaginasDePrivacidadeTests(TestCase):
    def test_pagina_de_dados_exige_login(self):
        self.assertEqual(self.client.get(reverse("minha_privacidade")).status_code, 302)

    def test_pagina_de_dados_responde_logado(self):
        self.client.force_login(criar_usuario("logada@exemplo.test"))
        self.assertEqual(self.client.get(reverse("minha_privacidade")).status_code, 200)

    def test_politica_aponta_para_a_pagina_de_dados(self):
        """A política não pode prometer o que a interface não entrega."""
        resposta = self.client.get(reverse("privacidade"))
        self.assertContains(resposta, reverse("minha_privacidade"))

    def test_existe_canal_de_contato(self):
        resposta = self.client.get(reverse("contato"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "mailto:")
