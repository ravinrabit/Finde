import gzip
import http.client
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


def _enderecos_seguros(host):
    try:
        enderecos = socket.getaddrinfo(host, None)
    except socket.gaierror as erro:
        raise FonteIndisponivel(f"Não foi possível resolver {host}: {erro}") from erro
    if not enderecos:
        raise FonteIndisponivel(f"Não foi possível resolver {host}")
    ips = []
    for _familia, _tipo, _proto, _nome, endereco in enderecos:
        ip = endereco[0]
        if _ip_bloqueado(ip):
            raise FonteIndisponivel(f"Destino não permitido: {host} resolve para {ip}")
        if ip not in ips:
            ips.append(ip)
    return ips


def validar_destino(url):
    """Checagem antecipada (mensagem de erro melhor, falha rápida). Quem
    garante a segurança de verdade é _conectar_em_ip_validado: como o DNS de
    um domínio malicioso pode responder um IP público aqui e um IP interno
    segundos depois ("DNS rebinding"), resolver e checar aqui não basta —
    dava pra passar nesta checagem e mesmo assim conectar num IP bloqueado
    se a conexão real resolvesse o host de novo, na hora de conectar.
    """
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ESQUEMAS_PERMITIDOS:
        raise FonteIndisponivel(f"Esquema não permitido em {url}")
    host = partes.hostname
    if not host:
        raise FonteIndisponivel(f"URL sem host em {url}")
    _enderecos_seguros(host)


def _conectar_em_ip_validado(enderecos):
    def _conectar(endereco, timeout, source_address=None):
        _host, porta = endereco
        ultimo_erro = None
        for ip in enderecos:
            try:
                return socket.create_connection((ip, porta), timeout, source_address)
            except OSError as erro:
                ultimo_erro = erro
        raise ultimo_erro

    return _conectar


class _HandlerHTTPFixo(urllib.request.HTTPHandler):
    def http_open(self, req):
        def fabrica(host, **kwargs):
            conexao = http.client.HTTPConnection(host, **kwargs)
            conexao._create_connection = _conectar_em_ip_validado(_enderecos_seguros(conexao.host))
            return conexao

        return self.do_open(fabrica, req)


class _HandlerHTTPSFixo(urllib.request.HTTPSHandler):
    def https_open(self, req):
        def fabrica(host, **kwargs):
            conexao = http.client.HTTPSConnection(host, **kwargs)
            conexao._create_connection = _conectar_em_ip_validado(_enderecos_seguros(conexao.host))
            return conexao

        return self.do_open(fabrica, req, context=self._context)


def _abrir(url, cabecalhos=None, timeout=None):
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
    # Handlers próprios (não o HTTPHandler/HTTPSHandler padrão do urllib):
    # eles conectam direto no IP já validado por _enderecos_seguros, em vez
    # de deixar o socket resolver o host de novo — inclusive num redirect,
    # que passa pelos mesmos handlers.
    opener = urllib.request.build_opener(_HandlerHTTPFixo, _HandlerHTTPSFixo)
    with opener.open(pedido, timeout=timeout or settings.INGESTAO_HTTP_TIMEOUT) as resposta:
        bruto = resposta.read(TAMANHO_MAXIMO + 1)
        if len(bruto) > TAMANHO_MAXIMO:
            raise FonteIndisponivel(f"Resposta grande demais em {url}")
        if resposta.headers.get("Content-Encoding") == "gzip":
            bruto = gzip.decompress(bruto)
        codificacao = resposta.headers.get_content_charset() or "utf-8"
        return bruto.decode(codificacao, errors="replace")


def robots_permite(url):
    try:
        partes = urllib.parse.urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        chave = f"robots:{base}"
        regras = cache.get(chave)
        if regras is None:
            leitor = RobotFileParser()
            url_robots = f"{base}/robots.txt"
            validar_destino(url_robots)
            try:
                texto = _abrir(url_robots)
            except urllib.error.HTTPError as erro:
                if erro.code in (401, 403):
                    leitor.disallow_all = True
                elif 400 <= erro.code < 500:
                    leitor.allow_all = True
            else:
                leitor.parse(texto.splitlines())
            regras = leitor
            cache.set(chave, regras, 60 * 60 * 6)
        return regras.can_fetch(user_agent(), url)
    except Exception:
        return True


def buscar(url, cabecalhos=None, timeout=None, checar_robots=True):
    validar_destino(url)

    if checar_robots and not robots_permite(url):
        raise FonteIndisponivel(f"robots.txt proíbe o acesso a {url}")

    try:
        return _abrir(url, cabecalhos, timeout)
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
