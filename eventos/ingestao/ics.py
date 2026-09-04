"""Leitor de feeds iCalendar (.ics).

Muitos espaços culturais, universidades e coletivos publicam a programação num
Google Agenda público. O formato é estável, o dado é aberto e o custo de manter
o conector é quase zero. Em compensação o dado é pobre: título, data e local —
sem imagem, sem preço, sem categoria. Serve como complemento, não como fonte
principal.

Sem dependência: um VEVENT é texto com "chave:valor" e continuação por espaço.
"""

import logging
from datetime import UTC, datetime, timedelta

from django.utils import timezone

from .base import EventoImportado, garantir_aware
from .http import buscar

logger = logging.getLogger("eventos.ingestao")


def desdobrar(texto):
    """Junta linhas continuadas (a RFC dobra em 75 octetos com espaço à frente)."""
    linhas = []
    for linha in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if linha[:1] in (" ", "\t") and linhas:
            linhas[-1] += linha[1:]
        else:
            linhas.append(linha)
    return linhas


def desescapar(valor):
    return (
        valor.replace("\\n", "\n").replace("\\N", "\n")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    )


def ler_data(valor, parametros):
    """DTSTART em UTC, com fuso nomeado, ou só a data."""
    valor = valor.strip()
    try:
        if valor.endswith("Z"):
            bruto = datetime.strptime(valor, "%Y%m%dT%H%M%SZ")
            # UTC vem da biblioteca padrão: django.utils.timezone.utc saiu no
            # Django 5.0 e o "Z" do iCalendar significa exatamente UTC.
            return bruto.replace(tzinfo=UTC)
        if "T" in valor:
            bruto = datetime.strptime(valor, "%Y%m%dT%H%M%S")
            return garantir_aware(bruto)
        if parametros.get("VALUE") == "DATE" or len(valor) == 8:
            bruto = datetime.strptime(valor, "%Y%m%d")
            return garantir_aware(bruto)
    except ValueError:
        return None
    return None


def _partir(linha):
    nome, _, valor = linha.partition(":")
    pedacos = nome.split(";")
    chave = pedacos[0].upper()
    parametros = {}
    for extra in pedacos[1:]:
        k, _, v = extra.partition("=")
        parametros[k.upper()] = v
    return chave, parametros, valor


def eventos_do_feed(texto, url_origem, prefixo_id="ics"):
    achados, atual = [], None

    for linha in desdobrar(texto):
        if linha.strip() == "BEGIN:VEVENT":
            atual = {}
            continue
        if linha.strip() == "END:VEVENT":
            if atual is not None:
                importado = _montar(atual, url_origem, prefixo_id)
                if importado:
                    achados.append(importado)
            atual = None
            continue
        if atual is None or ":" not in linha:
            continue
        chave, parametros, valor = _partir(linha)
        atual[chave] = (parametros, valor)

    return achados


def _montar(bruto, url_origem, prefixo_id):
    def campo(nome, padrao=""):
        return desescapar(bruto.get(nome, ({}, padrao))[1]).strip()

    inicio = None
    if "DTSTART" in bruto:
        parametros, valor = bruto["DTSTART"]
        inicio = ler_data(valor, parametros)
    if not inicio:
        return None

    fim = None
    if "DTEND" in bruto:
        parametros, valor = bruto["DTEND"]
        fim = ler_data(valor, parametros)
    elif "DURATION" in bruto:
        fim = inicio + timedelta(hours=2)

    uid = campo("UID") or f"{campo('SUMMARY')}-{inicio:%Y%m%d%H%M}"
    nome = campo("SUMMARY")
    if not nome:
        return None

    return EventoImportado(
        id_externo=f"{prefixo_id}:{uid}"[:120],
        nome=nome[:300],
        data=inicio,
        data_fim=fim,
        local=campo("LOCATION")[:300] or "A confirmar",
        descricao=campo("DESCRIPTION")[:4000],
        link_original=(campo("URL") or url_origem)[:600],
    )


def coletar(url, prefixo_id="ics", limite=None, **_):
    """Baixa um .ics e devolve EventoImportado só dos eventos futuros."""
    texto = buscar(url, checar_robots=False)
    agora = timezone.now()
    achados = [e for e in eventos_do_feed(texto, url, prefixo_id) if e.data >= agora]
    achados.sort(key=lambda e: e.data)
    logger.info("%d evento(s) futuro(s) no feed %s", len(achados), url)
    return achados[:limite] if limite else achados
