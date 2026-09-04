"""Conector de parceiros: espaços culturais que autorizaram a leitura.

Diferença essencial para o scraper que este projeto tinha: aqui existe uma
lista curta, conhecida e acordada, o acesso é por `requests` simples (sem
navegador), o robots.txt é respeitado e a página do evento leva crédito e link
de volta para o parceiro. Em troca da autorização, o parceiro ganha tráfego.

Cada parceiro declara como publica a agenda:
  tipo="ics"     -> feed iCalendar (Google Agenda público, por exemplo)
  tipo="jsonld"  -> página de agenda com schema.org/Event
  tipo="pagina"  -> uma página por evento; `links` traz a listagem a percorrer

A lista abaixo vem com os espaços mais prováveis do DF já mapeados, mas TODAS
as URLs estão como None de propósito: preencher sem falar com o parceiro é
voltar a raspar. Preencha `feed` conforme cada acordo for fechado.
"""

import logging
import re
import time

from django.utils import timezone

from . import ics, jsonld
from .http import FonteIndisponivel, buscar

logger = logging.getLogger("eventos.ingestao")

PAUSA_ENTRE_PAGINAS = 1.5


class Parceiro:
    def __init__(self, slug, nome, tipo, feed=None, regiao="", padrao_link=None, ativo=False):
        self.slug = slug
        self.nome = nome
        self.tipo = tipo
        self.feed = feed
        self.regiao = regiao
        self.padrao_link = padrao_link
        self.ativo = ativo and bool(feed)


# Preencha `feed` e marque ativo=True conforme cada acordo for fechado.
PARCEIROS = [
    Parceiro("cine-brasilia", "Cine Brasília", "jsonld", regiao="asa-sul"),
    Parceiro("clube-do-choro", "Clube do Choro", "jsonld", regiao="asa-sul"),
    Parceiro("teatro-nacional", "Teatro Nacional Cláudio Santoro", "jsonld", regiao="plano-piloto"),
    Parceiro("ccbb-brasilia", "CCBB Brasília", "jsonld", regiao="plano-piloto"),
    Parceiro("caixa-cultural", "Caixa Cultural Brasília", "jsonld", regiao="plano-piloto"),
    Parceiro("sesc-df", "Sesc-DF", "ics", regiao=""),
    Parceiro("complexo-planaltina", "Complexo Cultural de Planaltina", "ics", regiao="planaltina"),
    Parceiro("casa-do-cantador", "Casa do Cantador", "ics", regiao="ceilandia"),
    Parceiro("unb-agenda", "UnB — agenda de eventos", "ics", regiao="asa-norte"),
]

PARCEIROS_POR_SLUG = {p.slug: p for p in PARCEIROS}


def _links_da_listagem(html, padrao, base):
    from urllib.parse import urljoin

    encontrados, vistos = [], set()
    for href in re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE):
        if padrao and not re.search(padrao, href):
            continue
        url = urljoin(base, href.split("#")[0])
        if url not in vistos:
            vistos.add(url)
            encontrados.append(url)
    return encontrados


def coletar_parceiro(parceiro, limite=50):
    if not parceiro.ativo:
        logger.info("Parceiro %s sem feed configurado — ignorado.", parceiro.slug)
        return []

    try:
        if parceiro.tipo == "ics":
            achados = ics.coletar(parceiro.feed, prefixo_id=parceiro.slug, limite=limite)
        elif parceiro.tipo == "jsonld":
            achados = jsonld.ler_pagina(parceiro.feed)
        elif parceiro.tipo == "pagina":
            html = buscar(parceiro.feed)
            achados = []
            for url in _links_da_listagem(html, parceiro.padrao_link, parceiro.feed)[:limite]:
                time.sleep(PAUSA_ENTRE_PAGINAS)
                try:
                    achados.extend(jsonld.ler_pagina(url))
                except FonteIndisponivel as erro:
                    logger.warning("Página do parceiro %s falhou: %s", parceiro.slug, erro)
        else:
            logger.error("Tipo de parceiro desconhecido: %s", parceiro.tipo)
            return []
    except FonteIndisponivel as erro:
        logger.error("Parceiro %s indisponível: %s", parceiro.slug, erro)
        return []

    agora = timezone.now()
    for importado in achados:
        importado.id_externo = f"{parceiro.slug}:{importado.id_externo}"[:120]
        if parceiro.regiao and not importado.regiao:
            importado.regiao = parceiro.regiao
    return [e for e in achados if e.data and e.data >= agora][:limite]


def coletar(limite=200, slugs=None, **_):
    alvo = [PARCEIROS_POR_SLUG[s] for s in slugs if s in PARCEIROS_POR_SLUG] if slugs else PARCEIROS
    ativos = [p for p in alvo if p.ativo]
    if not ativos:
        logger.warning(
            "Nenhum parceiro ativo. Preencha `feed` em eventos/ingestao/parceiros.py "
            "conforme os acordos forem fechados."
        )
        return []
    achados = []
    for parceiro in ativos:
        achados.extend(coletar_parceiro(parceiro, limite=limite))
    achados.sort(key=lambda e: e.data)
    return achados[:limite]
