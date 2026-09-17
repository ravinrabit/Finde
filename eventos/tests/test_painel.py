from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, PlanoDestaque, Regiao
from ..models import Evento, Local, Produtor, SolicitacaoDestaque
from .base import criar_evento, criar_local, criar_produtor, criar_usuario


class AcessoAoPainelTests(TestCase):
    def test_visitante_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse("painel_evento_criar"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("login"), resposta.url)

    def test_usuario_comum_recebe_404(self):
        self.client.force_login(criar_usuario("comum@exemplo.test"))
        resposta = self.client.get(reverse("painel_evento_criar"))
        self.assertEqual(resposta.status_code, 404)


class EventoNoPainelTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("equipe@exemplo.test")
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)

    def dados(self, **extras):
        inicio = timezone.localtime() + timedelta(days=20)
        return {
            "nome": "Evento do Painel",
            "descricao": "Descrição de teste do painel administrativo.",
            "data": inicio.strftime("%Y-%m-%dT%H:%M"),
            "data_fim": "",
            "modalidade": "presencial",
            "local": "Espaço do Painel",
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

    def test_criacao_publica_direto_e_ganha_marcador(self):
        self.client.post(reverse("painel_evento_criar"), self.dados())
        evento = Evento.objects.get(nome="Evento do Painel")
        self.assertEqual(evento.status, Evento.Status.PUBLICADO)
        self.assertEqual(evento.fonte, "equipe")
        self.assertTrue(evento.tem_coordenadas)

    def test_edicao_de_pendente_para_publicado_avisa_por_email(self):
        evento = criar_evento(nome="Aguardando revisão", status=Evento.Status.PENDENTE)
        mail.outbox.clear()
        url = reverse("painel_evento_editar", args=[evento.slug])
        resposta = self.client.post(url, self.dados(nome=evento.nome, status=Evento.Status.PUBLICADO))
        self.assertEqual(resposta.status_code, 302)
        evento.refresh_from_db()
        self.assertEqual(evento.status, Evento.Status.PUBLICADO)

    def test_remover_exige_digitar_o_nome_exato(self):
        evento = criar_evento(nome="Para apagar")
        url = reverse("painel_evento_remover", args=[evento.slug])
        resposta = self.client.post(url, {"confirmacao": "nome errado"})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Evento.objects.filter(pk=evento.pk).exists())

        self.client.post(url, {"confirmacao": "Para apagar"})
        self.assertFalse(Evento.objects.filter(pk=evento.pk).exists())


class LocalNoPainelTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("equipe2@exemplo.test")
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)

    def test_criar_local_sem_coordenada_e_geocodificado_na_hora(self):
        resposta = self.client.post(reverse("painel_local_criar"), {
            "nome": "Espaço Novo do Painel",
            "endereco": "",
            "referencia": "",
            "regiao": Regiao.GAMA,
            "cidade": "Brasília",
            "cep": "",
            "descricao": "",
            "site": "",
            "latitude": "",
            "longitude": "",
        })
        self.assertEqual(resposta.status_code, 302)
        local = Local.objects.get(nome="Espaço Novo do Painel")
        self.assertTrue(local.tem_coordenadas)

    def test_nao_remove_local_com_evento_vinculado(self):
        local = criar_local(nome="Local Ocupado")
        criar_evento(local_ref=local)
        resposta = self.client.post(
            reverse("painel_local_remover", args=[local.slug]), {"confirmacao": "Local Ocupado"}
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Local.objects.filter(pk=local.pk).exists())


class ProdutorNoPainelTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("equipe3@exemplo.test")
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)

    def test_vincula_dono_pelo_email(self):
        produtor = criar_produtor(nome="Produtora Para Vincular")
        dono = criar_usuario("dono-produtor@exemplo.test")
        resposta = self.client.post(reverse("painel_produtor_editar", args=[produtor.slug]), {
            "nome": produtor.nome,
            "bio": "",
            "email": "",
            "site": "",
            "instagram": "",
            "whatsapp": "",
            "verificado": "on",
            "email_do_dono": dono.email,
        })
        self.assertEqual(resposta.status_code, 302)
        produtor.refresh_from_db()
        self.assertEqual(produtor.user_id, dono.pk)
        self.assertTrue(produtor.verificado)

    def test_email_do_dono_inexistente_e_recusado(self):
        produtor = criar_produtor(nome="Produtora Sem Dono")
        resposta = self.client.post(reverse("painel_produtor_editar", args=[produtor.slug]), {
            "nome": produtor.nome,
            "bio": "",
            "email": "",
            "site": "",
            "instagram": "",
            "whatsapp": "",
            "email_do_dono": "ninguem@exemplo.test",
        })
        self.assertFormError(resposta.context["form"], "email_do_dono", "Não existe conta com este e-mail.")

    def test_nao_remove_produtor_com_evento_vinculado(self):
        produtor = criar_produtor(nome="Produtora Ocupada")
        criar_evento(produtor=produtor)
        resposta = self.client.post(
            reverse("painel_produtor_remover", args=[produtor.slug]), {"confirmacao": "Produtora Ocupada"}
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Produtor.objects.filter(pk=produtor.pk).exists())


class SolicitarDestaqueTests(TestCase):
    def setUp(self):
        self.dono = criar_usuario("dono-destaque@exemplo.test")
        self.client.force_login(self.dono)
        self.evento = criar_evento(
            nome="Evento a Destacar", criado_por=self.dono, status=Evento.Status.PUBLICADO
        )

    def test_produtor_pode_pedir_destaque(self):
        resposta = self.client.post(
            reverse("solicitar_destaque", args=[self.evento.slug]),
            {"plano": PlanoDestaque.DESTAQUE, "mensagem": "Prioridade pro fim de semana"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            SolicitacaoDestaque.objects.filter(evento=self.evento, atendida=False).exists()
        )

    def test_nao_deixa_pedir_duas_vezes_enquanto_pendente(self):
        SolicitacaoDestaque.objects.create(evento=self.evento, plano=PlanoDestaque.DESTAQUE)
        self.client.post(
            reverse("solicitar_destaque", args=[self.evento.slug]),
            {"plano": PlanoDestaque.PREMIUM},
        )
        self.assertEqual(SolicitacaoDestaque.objects.filter(evento=self.evento).count(), 1)

    def test_nao_pode_pedir_destaque_de_evento_alheio(self):
        alheio = criar_evento(nome="Evento de outra pessoa")
        resposta = self.client.get(reverse("solicitar_destaque", args=[alheio.slug]))
        self.assertEqual(resposta.status_code, 404)


class DestaquePainelTests(TestCase):
    def setUp(self):
        self.staff = criar_usuario("equipe-destaque@exemplo.test")
        self.staff.is_staff = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.evento = criar_evento(nome="Evento Pedindo Destaque")
        self.solicitacao = SolicitacaoDestaque.objects.create(
            evento=self.evento, plano=PlanoDestaque.PREMIUM
        )

    def test_aprovar_ativa_o_plano_no_evento(self):
        self.client.post(reverse("painel_destaque_aprovar", args=[self.solicitacao.pk]))
        self.evento.refresh_from_db()
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.evento.plano_destaque, PlanoDestaque.PREMIUM)
        self.assertTrue(self.evento.destaque_ativo)
        self.assertTrue(self.solicitacao.atendida)

    def test_recusar_nao_muda_o_plano(self):
        self.client.post(reverse("painel_destaque_recusar", args=[self.solicitacao.pk]))
        self.evento.refresh_from_db()
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.evento.plano_destaque, PlanoDestaque.NORMAL)
        self.assertTrue(self.solicitacao.atendida)
