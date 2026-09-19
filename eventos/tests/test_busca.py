from django.test import TestCase

from ..models import Evento
from ..services import busca
from .base import criar_evento


class AplicarBuscaTests(TestCase):
    def setUp(self):
        self.evento = criar_evento(nome="Festival de Jazz do Cerrado")

    def test_todos_os_termos_precisam_bater_por_padrao(self):
        eventos = Evento.objects.all()
        self.assertIn(self.evento, busca.aplicar(eventos, "jazz cerrado"))
        self.assertNotIn(self.evento, busca.aplicar(eventos, "jazz rock"))

    def test_qualquer_termo_basta_quando_qualquer_e_true(self):
        eventos = Evento.objects.all()
        resultado = busca.aplicar(eventos, "jazz rock", qualquer=True)
        self.assertIn(self.evento, resultado)

    def test_consulta_em_linguagem_natural_ainda_encontra_o_evento(self):
        # Palavras de ligação ("quais", "tem", "em") não aparecem no texto do
        # evento — com AND estrito isso nunca bateria; com qualquer=True basta
        # "jazz" ou "cerrado" baterem.
        eventos = Evento.objects.all()
        resultado = busca.aplicar(
            eventos, "quais shows de jazz tem no cerrado", qualquer=True
        )
        self.assertIn(self.evento, resultado)
