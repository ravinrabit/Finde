from django.db import transaction

from ..constants import normalizar
from ..models import Evento, Local, Produtor
from . import geocoding


def resolver_local(nome, endereco="", regiao="", cidade="Brasília"):
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
    return produtor


def geocodificar_se_necessario(local):
    if local is None or local.tem_coordenadas or local.geocodificacao_falhou:
        return
    resultado = geocoding.geocodificar_local(local)
    if resultado != "falhou":
        Evento.objects.filter(local_ref=local).update(
            latitude=local.latitude, longitude=local.longitude
        )


@transaction.atomic
def salvar_evento_do_produtor(evento, user, original=None):
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
    geocodificar_se_necessario(evento.local_ref)
    if evento.local_ref_id:
        evento.refresh_from_db(fields=["latitude", "longitude"])
    return evento, voltaram


@transaction.atomic
def salvar_evento_da_equipe(evento):
    novo = evento.pk is None
    evento.local_ref = resolver_local(
        evento.local, evento.endereco, evento.regiao, evento.cidade
    )
    if evento.organizador:
        produtor = resolver_produtor(evento.organizador)
        if produtor is not None:
            evento.produtor = produtor
    if novo:
        evento.fonte = "equipe"

    evento.save()
    geocodificar_se_necessario(evento.local_ref)
    if evento.local_ref_id:
        evento.refresh_from_db(fields=["latitude", "longitude"])
    return evento


def aplicar_previa(formulario_dados, previa):
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
