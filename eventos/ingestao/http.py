"""Acesso HTTP dos conectores, com as boas maneiras no lugar certo.

urllib da biblioteca padrão: nenhuma dependência nova para buscar um JSON.
Todo conector passa por aqui, então User-Agent, timeout e limite de tamanho
valem para todos.
"""

import gzip
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("eventos.ingestao")

TAMANHO_MAXIMO = 5 * 1024 * 1024  # 5 MB: página de evento não passa disso


class FonteIndisponivel(Exception):
    """A fonte não respondeu, respondeu errado ou proibiu o acesso."""


def user_agent():
    return getattr(settings, "GEOCODING_USER_AGENT", f"Finde/1.0 (+https://{settings.SITE_DOMINIO})")


def robots_permite(url):
    """Respeita o robots.txt do host. Em dúvida, permite.

    Um conector de parceiro é autorizado, mas checar o robots é barato e evita
    a discussão de "vocês estão raspando meu site".
    """
    try:
        partes = urllib.parse.urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        chave = f"robots:{base}"
        regras = cache.get(chave)
        if regras is None:
            leitor = RobotFileParser()
            leitor.set_url(f"{base}/robots.txt")
            leitor.read()
            regras = leitor
            cache.set(chave, regras, 60 * 60 * 6)
        return regras.can_fetch(user_agent(), url)
    except Exception:
        return True


def buscar(url, cabecalhos=None, timeout=None, checar_robots=True):
    """Devolve o corpo em texto. Levanta FonteIndisponivel em qualquer falha."""
    if checar_robots and not robots_permite(url):
        raise FonteIndisponivel(f"robots.txt proíbe o acesso a {url}")

    pedido = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent(),
            "Accept": "text/html,application/json,text/calendar;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept-Encoding": "gzip",
            **(cabecalhos or {}),
        },
    )
    try:
        with urllib.request.urlopen(
            pedido, timeout=timeout or settings.INGESTAO_HTTP_TIMEOUT
        ) as resposta:
            bruto = resposta.read(TAMANHO_MAXIMO + 1)
            if len(bruto) > TAMANHO_MAXIMO:
                raise FonteIndisponivel(f"Resposta grande demais em {url}")
            if resposta.headers.get("Content-Encoding") == "gzip":
                bruto = gzip.decompress(bruto)
            codificacao = resposta.headers.get_content_charset() or "utf-8"
            return bruto.decode(codificacao, errors="replace")
    except urllib.error.HTTPError as erro:
        raise FonteIndisponivel(f"HTTP {erro.code} em {url}") from erro
    except Exception as erro:
        raise FonteIndisponivel(f"Falha ao acessar {url}: {erro}") from erro


def buscar_json(url, cabecalhos=None, timeout=None, checar_robots=False):
    texto = buscar(url, cabecalhos, timeout, checar_robots=checar_robots)
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise FonteIndisponivel(f"Resposta não é JSON válido em {url}") from erro
