"""Capacidade, limite por pessoa e concorrência.

BUG 5 — a reserva vivia dentro da view, sem transação e sem limite real: nada
impedia repetir a requisição mil vezes.
"""

from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from ..models import Evento, Ingresso
from ..services import reservas
from .base import criar_evento, criar_usuario


class ServicoDeReservaTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("pessoa@exemplo.test")
        self.evento = criar_evento(capacidade=5, limite_por_usuario=3)

    def test_reserva_cria_um_ingresso_por_unidade(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", 2)
        self.assertEqual(reserva.quantidade, 2)
        self.assertEqual(Ingresso.objects.count(), 2)

    def test_valor_da_meia_e_metade_com_centavos_certos(self):
        self.evento.preco = Decimal("80.50")
        self.evento.save()
        reserva = reservas.reservar(self.pessoa, self.evento, "meia", 1)
        self.assertEqual(reserva.valor_unitario, Decimal("40.25"))

    def test_limite_por_usuario_e_respeitado(self):
        reservas.reservar(self.pessoa, self.evento, "inteira", 3)
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.reservar(self.pessoa, self.evento, "inteira", 1)

    def test_limite_por_usuario_conta_reservas_anteriores(self):
        reservas.reservar(self.pessoa, self.evento, "inteira", 2)
        with self.assertRaises(reservas.ReservaInvalida) as erro:
            reservas.reservar(self.pessoa, self.evento, "inteira", 2)
        self.assertIn("mais 1", str(erro.exception))

    def test_capacidade_impede_overbooking(self):
        for indice in range(2):
            reservas.reservar(criar_usuario(f"p{indice}@exemplo.test"), self.evento, "inteira", 2)
        ultimo = criar_usuario("ultimo@exemplo.test")
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.reservar(ultimo, self.evento, "inteira", 3)
        self.assertEqual(self.evento.ingressos.count(), 4)

    def test_evento_esgotado_recusa_reserva(self):
        self.evento.capacidade = 1
        self.evento.save()
        reservas.reservar(self.pessoa, self.evento, "inteira", 1)
        outro = criar_usuario("outro@exemplo.test")
        with self.assertRaises(reservas.ReservaInvalida) as erro:
            reservas.reservar(outro, self.evento, "inteira", 1)
        self.assertIn("esgotado", str(erro.exception).lower())

    def test_capacidade_vazia_significa_sem_limite(self):
        self.evento.capacidade = None
        self.evento.limite_por_usuario = 10
        self.evento.save()
        self.assertIsNone(reservas.vagas_restantes(self.evento))
        self.assertFalse(self.evento.esgotado)

    def test_cancelamento_devolve_a_vaga(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", 2)
        self.assertEqual(reservas.vagas_restantes(self.evento), 3)
        reservas.cancelar(reserva.ingressos[0])
        self.assertEqual(reservas.vagas_restantes(self.evento), 4)

    def test_evento_nao_publicado_recusa_reserva(self):
        self.evento.status = Evento.Status.PENDENTE
        self.evento.save()
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.reservar(self.pessoa, self.evento, "inteira", 1)

    def test_evento_passado_recusa_reserva(self):
        self.evento.data = timezone.now() - timedelta(days=1)
        self.evento.save()
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.reservar(self.pessoa, self.evento, "inteira", 1)

    def test_quantidade_invalida_vira_um(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", "abacaxi")
        self.assertEqual(reserva.quantidade, 1)

    def test_quantidade_negativa_vira_um(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", -5)
        self.assertEqual(reserva.quantidade, 1)

    def test_tipo_invalido_vira_inteira(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "vip", 1)
        self.assertEqual(reserva.tipo, Ingresso.Tipo.INTEIRA)

    def test_check_in_marca_utilizado(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", 1)
        ingresso = reservas.marcar_utilizado(reserva.ingressos[0])
        self.assertEqual(ingresso.status, Ingresso.Status.UTILIZADO)
        self.assertIsNotNone(ingresso.utilizado_em)

    def test_check_in_duas_vezes_e_recusado(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", 1)
        reservas.marcar_utilizado(reserva.ingressos[0])
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.marcar_utilizado(reserva.ingressos[0])

    def test_check_in_de_cancelado_e_recusado(self):
        reserva = reservas.reservar(self.pessoa, self.evento, "inteira", 1)
        reservas.cancelar(reserva.ingressos[0])
        with self.assertRaises(reservas.ReservaInvalida):
            reservas.marcar_utilizado(reserva.ingressos[0])


class ReservaPelaViewTests(TestCase):
    def setUp(self):
        self.pessoa = criar_usuario("view@exemplo.test")
        self.client.force_login(self.pessoa)
        self.evento = criar_evento(capacidade=2, limite_por_usuario=2)
        self.url = reverse("reservar_ingresso", args=[self.evento.slug])

    def test_reserva_bem_sucedida_envia_email(self):
        mail.outbox.clear()
        self.client.post(self.url, {"tipo": "inteira", "quantidade": 1})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reserva confirmada", mail.outbox[0].subject)

    def test_acima_da_capacidade_mostra_mensagem_em_vez_de_erro_500(self):
        self.client.post(self.url, {"tipo": "inteira", "quantidade": 2})
        outro = criar_usuario("outro-view@exemplo.test")
        self.client.force_login(outro)
        resposta = self.client.post(self.url, {"tipo": "inteira", "quantidade": 1}, follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.evento.ingressos.count(), 2)

    def test_contexto_expoe_o_maximo_permitido(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.context["maximo"], 2)
        self.assertEqual(resposta.context["vagas"], 2)


class ConcorrenciaTests(TransactionTestCase):
    """Duas reservas simultâneas não podem consumir a mesma última vaga.

    TransactionTestCase (e não TestCase) porque cada thread precisa da própria
    transação de verdade — dentro de uma transação de teste, o lock não vale.
    """

    def test_duas_reservas_simultaneas_nao_estouram_a_capacidade(self):
        import threading

        from django.db import connections

        evento = criar_evento(capacidade=1, limite_por_usuario=1)
        pessoas = [criar_usuario(f"corrida{i}@exemplo.test") for i in range(2)]
        erros, sucessos = [], []

        def tentar(pessoa):
            try:
                reservas.reservar(pessoa, evento, "inteira", 1)
                sucessos.append(pessoa)
            except reservas.ReservaInvalida:
                erros.append(pessoa)
            except Exception as erro:  # banco travado, etc.
                erros.append(erro)
            finally:
                connections.close_all()

        fios = [threading.Thread(target=tentar, args=(p,)) for p in pessoas]
        for fio in fios:
            fio.start()
        for fio in fios:
            fio.join(timeout=15)

        self.assertEqual(
            evento.ingressos.exclude(status=Ingresso.Status.CANCELADO).count(),
            1,
            "a capacidade foi estourada por reservas simultâneas",
        )
        self.assertEqual(len(sucessos), 1)
