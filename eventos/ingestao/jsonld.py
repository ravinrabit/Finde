"""Leitor de schema.org/Event embutido em página HTML.

Serve a dois usos:
  1. conector de parceiro autorizado (parceiros.py);
  2. "colar link" no formulário do produtor — o dono do evento pede
     explicitamente que o Finde leia a própria página dele.

Ler JSON-LD é muito mais estável do que adivinhar por seletores de CSS: é o
mesmo dado que o site já publica para o Google.
"""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_datetime

from .base import EventoImportado, garantir_aware
from .http import FonteIndisponivel, buscar

BLOCO_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
META_OG = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:([a-z:]+)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE,
)
TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


def ler_data(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return garantir_aware(valor)
    analisada = parse_datetime(str(valor))
    if analisada:
        return garantir_aware(analisada)
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return garantir_aware(datetime.strptime(str(valor).strip(), formato))
        except ValueError:
            continue
    return None


def ler_local(location):
    if isinstance(location, list):
        location = next((x for x in location if isinstance(x, dict)), None)
    if not isinstance(location, dict):
        return "", "", None, None

    nome = (location.get("name") or "").strip()
    endereco = location.get("address")
    if isinstance(endereco, dict):
        partes = [
            endereco.get("streetAddress"),
            endereco.get("addressLocality"),
            endereco.get("addressRegion"),
        ]
        texto = ", ".join(str(p).strip() for p in partes if p)
    elif isinstance(endereco, str):
        texto = endereco.strip()
    else:
        texto = ""

    lat = lon = None
    geo = location.get("geo")
    if isinstance(geo, dict):
        try:
            lat = float(geo.get("latitude"))
            lon = float(geo.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
    return nome, texto, lat, lon


def ler_oferta(offers):
    if not offers:
        return None, False
    lista = offers if isinstance(offers, list) else [offers]
    valores = []
    for oferta in lista:
        if not isinstance(oferta, dict):
            continue
        bruto = oferta.get("price", oferta.get("lowPrice"))
        if bruto in (None, ""):
            continue
        try:
            valores.append(Decimal(str(bruto).replace(",", ".")))
        except InvalidOperation:
            continue
    if not valores:
        return None, False
    menor = min(valores)
    return (None, True) if menor == 0 else (menor, False)


def ler_organizador(organizer):
    if isinstance(organizer, list):
        organizer = next((x for x in organizer if x), None)
    if isinstance(organizer, dict):
        return (organizer.get("name") or "").strip()
    if isinstance(organizer, str):
        return organizer.strip()
    return ""


def ler_imagem(image):
    if isinstance(image, list):
        primeira = next((i for i in image if i), None)
        return ler_imagem(primeira)
    if isinstance(image, dict):
        return image.get("url", "") or ""
    return image if isinstance(image, str) else ""


def _achatar(dados):
    """JSON-LD aceita lista, objeto solto e @graph. Achata tudo em uma lista."""
    pilha, saida = [dados], []
    while pilha:
        item = pilha.pop()
        if isinstance(item, list):
            pilha.extend(item)
        elif isinstance(item, dict):
            saida.append(item)
            if isinstance(item.get("@graph"), (list, dict)):
                pilha.append(item["@graph"])
    return saida


def extrair_blocos(html):
    """Todos os objetos cujo @type contém 'Event'."""
    encontrados = []
    for bruto in BLOCO_LD.findall(html):
        try:
            dados = json.loads(bruto.strip())
        except json.JSONDecodeError:
            continue
        for item in _achatar(dados):
            tipo = item.get("@type", "")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if any("Event" in str(t) for t in tipos):
                encontrados.append(item)
    return encontrados


def para_importado(bloco, url, id_externo=None):
    inicio = ler_data(bloco.get("startDate"))
    if not inicio:
        return None
    nome_local, endereco, lat, lon = ler_local(bloco.get("location"))
    preco, gratuito = ler_oferta(bloco.get("offers"))
    return EventoImportado(
        id_externo=(id_externo or url)[:120],
        nome=(bloco.get("name") or "").strip()[:300],
        data=inicio,
        data_fim=ler_data(bloco.get("endDate")),
        local=nome_local or "A confirmar",
        endereco=endereco,
        descricao=(bloco.get("description") or "").strip()[:4000],
        organizador=ler_organizador(bloco.get("organizer")),
        imagem_url=ler_imagem(bloco.get("image")),
        link_original=url,
        preco=preco,
        gratuito=gratuito,
        latitude=lat,
        longitude=lon,
    )


def ler_pagina(url, id_externo=None, checar_robots=True):
    """Devolve a lista de EventoImportado encontrados na página."""
    html = buscar(url, checar_robots=checar_robots)
    achados = []
    for bloco in extrair_blocos(html):
        importado = para_importado(bloco, url, id_externo)
        if importado:
            achados.append(importado)
    return achados


def previa_de_link(url):
    """Melhor esforço para pré-preencher o formulário a partir de um link.

    Tenta JSON-LD; se não houver, cai para Open Graph. Devolve um dicionário
    com o que conseguiu — o produtor confere e corrige antes de enviar.
    """
    try:
        html = buscar(url, checar_robots=True)
    except FonteIndisponivel as erro:
        return {"erro": str(erro)}

    blocos = extrair_blocos(html)
    if blocos:
        importado = para_importado(blocos[0], url)
        if importado:
            return {
                "nome": importado.nome,
                "descricao": importado.descricao,
                "data": importado.data,
                "data_fim": importado.data_fim,
                "local": importado.local,
                "endereco": importado.endereco,
                "organizador": importado.organizador,
                "imagem_url": importado.imagem_url,
                "preco": importado.preco,
                "gratuito": importado.gratuito,
                "link_original": url,
                "origem": "schema.org/Event",
            }

    og = {chave: valor for chave, valor in META_OG.findall(html)}
    titulo = og.get("title") or ""
    if not titulo:
        achado = TITULO.search(html)
        titulo = achado.group(1).strip() if achado else ""
    if not titulo:
        return {"erro": "A página não publica dados estruturados de evento."}
    return {
        "nome": titulo[:300],
        "descricao": (og.get("description") or "")[:4000],
        "imagem_url": og.get("image", ""),
        "link_original": url,
        "origem": "Open Graph (incompleto — confira data e local)",
    }
