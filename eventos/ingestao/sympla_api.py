"""Sympla pela API oficial, com token cedido pelo produtor.

A API pública da Sympla devolve APENAS os eventos do dono do token — ela não
tem busca por cidade. Isso descarta a Sympla como fonte de agregação, mas abre
uma porta melhor: o produtor que já usa Sympla conecta a conta e os eventos
dele passam a aparecer no Finde sozinhos, para sempre, sem digitar nada.

Vira argumento de aquisição em vez de risco jurídico.

Endpoint: GET https://api.sympla.com.br/public/v1.5.1/events
Autenticação: cabeçalho s_token.
"""

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .base import EventoImportado, garantir_aware
from .http import FonteIndisponivel, buscar_json

logger = logging.getLogger("eventos.ingestao")

BASE = "https://api.sympla.com.br/public/v1.5.1"
FONTE = "sympla-produtor"


def _data(valor):
    if not valor:
        return None
    texto = str(valor).strip().replace("T", " ").split(".")[0]
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return garantir_aware(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return None


def _endereco(address):
    if not isinstance(address, dict):
        return "", "", None, None
    partes = [
        address.get("address"),
        address.get("address_num"),
        address.get("neighborhood"),
    ]
    texto = ", ".join(str(p).strip() for p in partes if p)
    nome = str(address.get("name") or "").strip()
    try:
        lat = float(address["lat"])
        lon = float(address["lon"])
    except (KeyError, TypeError, ValueError):
        lat = lon = None
    return nome, texto, lat, lon


def _preco(bruto):
    if bruto in (None, ""):
        return None, False
    try:
        valor = Decimal(str(bruto).replace(",", "."))
    except InvalidOperation:
        return None, False
    return (None, True) if valor == 0 else (valor, False)


def para_importado(bruto):
    inicio = _data(bruto.get("start_date"))
    if not inicio:
        return None
    nome_local, endereco, lat, lon = _endereco(bruto.get("address"))
    preco, gratuito = _preco(bruto.get("min_price"))
    cidade = ""
    if isinstance(bruto.get("address"), dict):
        cidade = str(bruto["address"].get("city") or "").strip()

    return EventoImportado(
        id_externo=f"sympla:{bruto.get('id')}"[:120],
        nome=str(bruto.get("name") or "").strip()[:300],
        data=inicio,
        data_fim=_data(bruto.get("end_date")),
        local=nome_local[:300] or "A confirmar",
        endereco=endereco[:300],
        descricao=str(bruto.get("detail") or "")[:4000],
        imagem_url=str(bruto.get("image") or "")[:600],
        link_original=str(bruto.get("url") or "")[:600],
        preco=preco,
        gratuito=gratuito,
        latitude=lat,
        longitude=lon,
        cidade=cidade or "Brasília",
    )


def coletar_da_integracao(integracao, limite=100):
    """Eventos futuros da conta Sympla de um produtor."""
    desde = timezone.localdate().isoformat()
    url = f"{BASE}/events?from={desde}&page_size={int(limite)}&published=true"
    try:
        resposta = buscar_json(url, cabecalhos={"s_token": integracao.token})
    except FonteIndisponivel as erro:
        integracao.ultimo_erro = str(erro)[:500]
        integracao.save(update_fields=["ultimo_erro"])
        logger.error("Sympla falhou para %s: %s", integracao.produtor.nome, erro)
        return []

    dados = resposta.get("data") if isinstance(resposta, dict) else resposta
    achados = []
    for bruto in dados or []:
        importado = para_importado(bruto)
        if not importado:
            continue
        # O dono do token É o produtor: não se adivinha organizador.
        importado.organizador = integracao.produtor.nome
        achados.append(importado)

    integracao.ultimo_erro = ""
    integracao.ultima_sincronizacao = timezone.now()
    integracao.save(update_fields=["ultimo_erro", "ultima_sincronizacao"])
    return achados


def coletar(limite=100, **_):
    """Percorre todas as integrações ativas."""
    from ..models import IntegracaoSympla

    achados = []
    for integracao in IntegracaoSympla.objects.filter(ativa=True).select_related("produtor"):
        achados.extend(coletar_da_integracao(integracao, limite=limite))
    return achados
