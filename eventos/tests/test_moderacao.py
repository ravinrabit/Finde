"""BUG 4 — evento publicado podia ser editado sem voltar para revisão.

Bastava publicar algo inocente, esperar a aprovação e trocar nome, data, local
e preço depois. A moderação existia só no papel.
"""

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento
from .base import criar_evento, criar_usuario


class ModeracaoDeEdicaoTests(TestCase):
    def setUp(self):
        self.dono = criar_usuario("dono@exemplo.test")
        self.client.force_login(self.dono)
        self.evento = criar_evento(
            nome="Show aprovado",
            criado_por=self.dono,
            status=Evento.Status.PUBLICADO,
            descricao="Descrição original do evento.",
        )
        self.url = reverse("editar_evento", args=[self.evento.slug])

    def dados(self, **mudancas):
        base = {
            "nome": self.evento.nome,
            "resumo": "",
            "descricao": self.evento.descricao,
            "data": (timezone.localtime(self.evento.data)).strftime("%Y-%m-%dT%H:%M"),
            "data_fim": "",
            "modalidade": "presencial",
            "local": self.evento.local,
            "endereco": "",
            "regiao": Regiao.ASA_SUL,
            "cidade": "Brasília",
            "categoria": Categoria.MUSICA,
            "preco": "50.00",
            "limite_por_usuario": "10",
            "organizador": "",
            "link_ingressos": "",
        }
        base.update(mudancas)
        return base

    def test_mudar_a_data_devolve_para_revisao(self):
        nova = timezone.localtime(timezone.now() + timedelta(days=30))
        self.client.post(self.url, self.dados(data=nova.strftime("%Y-%m-%dT%H:%M")))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)

    def test_mudar_o_nome_devolve_para_revisao(self):
        self.client.post(self.url, self.dados(nome="Outro show completamente diferente"))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)

    def test_mudar_o_local_devolve_para_revisao(self):
        self.client.post(self.url, self.dados(local="Estádio Mané Garrincha"))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)

    def test_mudar_o_preco_devolve_para_revisao(self):
        self.client.post(self.url, self.dados(preco="900.00"))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)

    def test_mudar_so_a_descricao_mantem_publicado(self):
        """Corrigir um erro de digitação não pode tirar o evento do ar."""
        self.client.post(self.url, self.dados(descricao="Descrição revisada, sem erro de digitação."))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PUBLICADO)
        self.assertIn("revisada", self.evento.descricao)

    def test_publicado_em_e_zerado_ao_voltar_para_revisao(self):
        self.client.post(self.url, self.dados(nome="Nome trocado depois da aprovação"))
        self.evento.refresh_from_db()
        self.assertIsNone(self.evento.publicado_em)

    def test_produtor_e_avisado_quando_o_evento_volta(self):
        mail.outbox.clear()
        self.client.post(self.url, self.dados(nome="Nome trocado depois da aprovação"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("revisão", mail.outbox[0].subject.lower())

    def test_rejeitado_volta_para_pendente_e_limpa_o_motivo(self):
        self.evento.status = Evento.Status.REJEITADO
        self.evento.motivo_rejeicao = "Faltou o endereço completo."
        self.evento.save()

        self.client.post(self.url, self.dados(endereco="SDC Eixo Monumental, Lote 5"))
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)
        self.assertEqual(self.evento.motivo_rejeicao, "")


class PrecisaoDeDataTests(TestCase):
    """O widget de data tem precisão de minuto; o banco guarda segundos.

    Comparar os dois crus fazia "20:00:37" e "20:00:00" parecerem datas
    diferentes. Efeito: todo evento com segundos no banco — ou seja, todo
    evento importado — voltava para revisão só por ter a descrição salva, e
    um evento passado continuava impossível de corrigir.
    """

    def setUp(self):
        self.dono = criar_usuario("precisao@exemplo.test")
        self.client.force_login(self.dono)
        # Data COM segundos e microssegundos, como a importação grava.
        self.evento = criar_evento(
            nome="Evento com segundos na data",
            criado_por=self.dono,
            status=Evento.Status.PUBLICADO,
            data=(timezone.now() + timedelta(days=5)).replace(second=37, microsecond=481923),
        )

    def campos(self, **mudancas):
        base = {
            "nome": self.evento.nome,
            "resumo": "",
            "descricao": "Texto novo, data intocada.",
            # Exatamente o que o widget devolveria: truncado no minuto.
            "data": timezone.localtime(self.evento.data).strftime("%Y-%m-%dT%H:%M"),
            "data_fim": "",
            "modalidade": "presencial",
            "local": self.evento.local,
            "endereco": "",
            "regiao": Regiao.ASA_SUL,
            "cidade": "Brasília",
            "categoria": Categoria.MUSICA,
            "preco": "50.00",
            "limite_por_usuario": "10",
            "organizador": "",
            "link_ingressos": "",
        }
        base.update(mudancas)
        return base

    def test_reenviar_a_mesma_data_nao_devolve_para_revisao(self):
        self.client.post(reverse("editar_evento", args=[self.evento.slug]), self.campos())
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PUBLICADO)
        self.assertIn("intocada", self.evento.descricao)

    def test_mudanca_real_de_horario_ainda_devolve_para_revisao(self):
        nova = timezone.localtime(self.evento.data + timedelta(hours=3))
        self.client.post(
            reverse("editar_evento", args=[self.evento.slug]),
            self.campos(data=nova.strftime("%Y-%m-%dT%H:%M")),
        )
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.status, Evento.Status.PENDENTE)

    def test_evento_passado_com_segundos_pode_ser_corrigido(self):
        self.evento.data = (timezone.now() - timedelta(days=10)).replace(
            second=37, microsecond=481923
        )
        self.evento.save()
        resposta = self.client.post(
            reverse("editar_evento", args=[self.evento.slug]),
            self.campos(data=timezone.localtime(self.evento.data).strftime("%Y-%m-%dT%H:%M")),
        )
        self.assertEqual(resposta.status_code, 302, "o formulário recusou uma data inalterada")
        self.evento.refresh_from_db()
        self.assertIn("intocada", self.evento.descricao)


class EdicaoDeEventoPassadoTests(TestCase):
    """BUG 8 — clean_data exigia data futura também na edição.

    Quem errou a data e deixou passar ficava com o formulário permanentemente
    inválido, sem conseguir corrigir nem a descrição.
    """

    def setUp(self):
        self.dono = criar_usuario("dono2@exemplo.test")
        self.client.force_login(self.dono)
        self.evento = criar_evento(
            nome="Evento que já passou",
            criado_por=self.dono,
            data=timezone.now() - timedelta(days=10),
            status=Evento.Status.PUBLICADO,
        )

    def test_edita_descricao_de_evento_passado(self):
        antiga = timezone.localtime(self.evento.data).strftime("%Y-%m-%dT%H:%M")
        resposta = self.client.post(
            reverse("editar_evento", args=[self.evento.slug]),
            {
                "nome": self.evento.nome,
                "resumo": "",
                "descricao": "Texto corrigido depois do evento.",
                "data": antiga,
                "data_fim": "",
                "modalidade": "presencial",
                "local": self.evento.local,
                "endereco": "",
                "regiao": Regiao.ASA_SUL,
                "cidade": "Brasília",
                "categoria": Categoria.MUSICA,
                "preco": "50.00",
                "limite_por_usuario": "10",
                "organizador": "",
                "link_ingressos": "",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.evento.refresh_from_db()
        self.assertIn("corrigido", self.evento.descricao)

    def test_mover_para_o_passado_continua_recusado(self):
        """Corrigir é uma coisa; agendar um evento para ontem é outra."""
        passado = timezone.localtime(timezone.now() - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M")
        resposta = self.client.post(
            reverse("editar_evento", args=[self.evento.slug]),
            {
                "nome": self.evento.nome,
                "resumo": "",
                "descricao": "x",
                "data": passado,
                "data_fim": "",
                "modalidade": "presencial",
                "local": self.evento.local,
                "endereco": "",
                "regiao": Regiao.ASA_SUL,
                "cidade": "Brasília",
                "categoria": Categoria.MUSICA,
                "preco": "50.00",
                "limite_por_usuario": "10",
                "organizador": "",
                "link_ingressos": "",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFormError(resposta.context["form"], "data", "A data de início precisa ser no futuro.")
