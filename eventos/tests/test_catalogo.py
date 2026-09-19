from unittest.mock import patch

from django.test import TestCase

from ..models import Local, Produtor
from ..services import catalogo
from .base import criar_evento, criar_local, criar_produtor


def _forcar_nao_encontrado(gerente, campo_chave):
    """Envolve gerente.filter para devolver queryset vazio só quando a busca é
    pelo campo de deduplicação — outras chamadas (ex.: unicidade de slug em
    gerar_slug) continuam batendo no banco de verdade."""
    original = gerente.filter

    def filtro(*args, **kwargs):
        qs = original(*args, **kwargs)
        return qs.none() if campo_chave in kwargs else qs

    return filtro


class ResolverLocalCorridaTests(TestCase):
    def test_corrida_entre_filter_e_create_cai_no_registro_existente(self):
        existente = criar_local(nome="Espaço Cultural X")
        # Simula duas requisições batendo no filter() ao mesmo tempo: a
        # segunda não vê o local que a primeira acabou de criar.
        with patch(
            "eventos.services.catalogo.Local.objects.filter",
            side_effect=_forcar_nao_encontrado(Local.objects, "nome_normalizado"),
        ):
            resultado = catalogo.resolver_local("Espaço Cultural X")

        self.assertEqual(resultado.pk, existente.pk)
        self.assertEqual(Local.objects.filter(nome_normalizado="espaco cultural x").count(), 1)


class ResolverProdutorCorridaTests(TestCase):
    def test_corrida_entre_filter_e_create_cai_no_registro_existente(self):
        existente = criar_produtor(nome="Produtora Cerrado")
        with patch(
            "eventos.services.catalogo.Produtor.objects.filter",
            side_effect=_forcar_nao_encontrado(Produtor.objects, "nome_normalizado"),
        ):
            resultado = catalogo.resolver_produtor("Produtora Cerrado")

        self.assertEqual(resultado.pk, existente.pk)
        self.assertEqual(Produtor.objects.filter(nome_normalizado="produtora cerrado").count(), 1)


class OrganizadorNomeTests(TestCase):
    def test_prioriza_o_texto_digitado_sobre_o_nome_do_perfil(self):
        produtor = criar_produtor(nome="Produtora Cerrado")
        evento = criar_evento(produtor=produtor, organizador="Coprodução Especial")
        self.assertEqual(evento.organizador_nome, "Coprodução Especial")

    def test_usa_o_nome_do_perfil_quando_organizador_esta_vazio(self):
        produtor = criar_produtor(nome="Produtora Cerrado")
        evento = criar_evento(produtor=produtor, organizador="")
        self.assertEqual(evento.organizador_nome, "Produtora Cerrado")
