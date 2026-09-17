import gzip
import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("eventos.ingestao")

TAMANHO_MAXIMO = 5 * 1024 * 1024
ESQUEMAS_PERMITIDOS = {"http", "https"}


class FonteIndisponivel(Exception):
    pass


def user_agent():
    return getattr(settings, "GEOCODING_USER_AGENT", f"Finde/1.0 (+https://{settings.SITE_DOMINIO})")


def _ip_bloqueado(ip_texto):
    try:
        ip = ipaddress.ip_address(ip_texto)
    except ValueError:
        return True
    mapeado = getattr(ip, "ipv4_mapped", None)
    if mapeado is not None:
        ip = mapeado
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validar_destino(url):
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ESQUEMAS_PERMITIDOS:
        raise FonteIndisponivel(f"Esquema não permitido em {url}")
    host = partes.hostname
    if not host:
        raise FonteIndisponivel(f"URL sem host em {url}")
    try:
        enderecos = socket.getaddrinfo(host, None)
    except socket.gaierror as erro:
        raise FonteIndisponivel(f"Não foi possível resolver {host}: {erro}") from erro
    if not enderecos:
        raise FonteIndisponivel(f"Não foi possível resolver {host}")
    for _familia, _tipo, _proto, _nome, endereco in enderecos:
        if _ip_bloqueado(endereco[0]):
            raise FonteIndisponivel(f"Destino não permitido: {host} resolve para {endereco[0]}")


class _RedirecionamentoValidado(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validar_destino(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def robots_permite(url):
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
    validar_destino(url)

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
    opener = urllib.request.build_opener(_RedirecionamentoValidado)
    try:
        with opener.open(pedido, timeout=timeout or settings.INGESTAO_HTTP_TIMEOUT) as resposta:
            bruto = resposta.read(TAMANHO_MAXIMO + 1)
            if len(bruto) > TAMANHO_MAXIMO:
                raise FonteIndisponivel(f"Resposta grande demais em {url}")
            if resposta.headers.get("Content-Encoding") == "gzip":
                bruto = gzip.decompress(bruto)
            codificacao = resposta.headers.get_content_charset() or "utf-8"
            return bruto.decode(codificacao, errors="replace")
    except urllib.error.HTTPError as erro:
        raise FonteIndisponivel(f"HTTP {erro.code} em {url}") from erro
    except FonteIndisponivel:
        raise
    except Exception as erro:
        raise FonteIndisponivel(f"Falha ao acessar {url}: {erro}") from erro


def buscar_json(url, cabecalhos=None, timeout=None, checar_robots=False):
    texto = buscar(url, cabecalhos, timeout, checar_robots=checar_robots)
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise FonteIndisponivel(f"Resposta não é JSON válido em {url}") from erro
