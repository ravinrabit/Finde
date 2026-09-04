"""Regras de catálogo que a view não deve carregar.

Resolver Local e Produtor a partir do que o produtor digitou, e decidir se uma
edição devolve o evento para a fila de revisão.
"""

from django.db import transaction

from ..constants import normalizar
from ..models import Evento, Local, Produtor


def resolver_local(nome, endereco="", regiao="", cidade="Brasília"):
    """Encontra o Local pelo nome normalizado ou cria um novo.

    É o que impede "Cine Brasília", "Cine Brasilia" e "cine brasília" de
    virarem três espaços diferentes.
    """
    nome = (nome or "").strip()[:200]
    if not nome:
        return None
    chave = normalizar(nome)[:200]
    local = Local.objects.filter(nome_normalizado=chave).first()
    if local:
        mudou = []
        if not local.endereco and endereco:
            local.endereco = endereco[:300]
            mudou.append("endereco")
        if not local.regiao and regiao:
            local.regiao = regiao
            mudou.append("regiao")
        if mudou:
            local.save(update_fields=mudou)
        return local
    return Local.objects.create(
        nome=nome, endereco=(endereco or "")[:300], regiao=regiao or "", cidade=cidade or "Brasília"
    )


def resolver_produtor(nome, user=None):
    """Um produtor por nome normalizado. Se o usuário já tem um, é o dele."""
    if user is not None:
        existente = Produtor.objects.filter(user=user).first()
        if existente:
            return existente
    nome = (nome or "").strip()[:200]
    if not nome:
        return None
    chave = normalizar(nome)[:200]
    produtor = Produtor.objects.filter(nome_normalizado=chave).first()
    if produtor is None:
        produtor = Produtor.objects.create(nome=nome, user=user)
    elif user is not None and produtor.user_id is None:
        produtor.user = user
        produtor.save(update_fields=["user"])
    return produtor


@transaction.atomic
def salvar_evento_do_produtor(evento, user, original=None):
    """Grava o evento vindo do formulário e aplica a política de moderação.

    Devolve (evento, campos_que_dispararam_revisao).

    A regra que faltava: um evento publicado que muda nome, data, local ou
    preço volta para a fila. Sem isso, bastava publicar algo inocente, esperar
    a aprovação e trocar o conteúdo depois.
    """
    evento.criado_por = evento.criado_por or user
    evento.local_ref = resolver_local(
        evento.local, evento.endereco, evento.regiao, evento.cidade
    )
    evento.produtor = resolver_produtor(evento.organizador, user=user)
    if evento.produtor and not evento.organizador:
        evento.organizador = evento.produtor.nome

    voltaram = []
    if original is None:
        evento.fonte = "produtor"
        evento.status = Evento.Status.PENDENTE
    else:
        voltaram = evento.alteracoes_sensiveis(original)
        if original.status == Evento.Status.REJEITADO:
            evento.status = Evento.Status.PENDENTE
            evento.motivo_rejeicao = ""
        elif original.status == Evento.Status.PUBLICADO and voltaram:
            evento.status = Evento.Status.PENDENTE
            evento.publicado_em = None

    evento.save()
    return evento, voltaram


def aplicar_previa(formulario_dados, previa):
    """Mescla o que veio do link colado com o que o produtor já digitou.

    O que o produtor escreveu sempre ganha: a prévia preenche buracos, nunca
    sobrescreve.
    """
    mapa = {
        "nome": "nome",
        "descricao": "descricao",
        "local": "local",
        "endereco": "endereco",
        "organizador": "organizador",
        "preco": "preco",
        "gratuito": "gratuito",
        "data": "data",
        "data_fim": "data_fim",
    }
    dados = dict(formulario_dados)
    for origem, destino in mapa.items():
        valor = previa.get(origem)
        if valor in (None, "", False) or dados.get(destino):
            continue
        dados[destino] = valor
    return dados
