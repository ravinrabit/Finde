"""Geocodificação de endereços do DF via Nominatim/OpenStreetMap.

Regras de uso do Nominatim que este módulo respeita, porque quebrar isso
significa ser bloqueado e derrubar o mapa do produto:
  - no máximo 1 requisição por segundo (GEOCODING_PAUSA_SEGUNDOS);
  - User-Agent identificando a aplicação e um contato;
  - resultado em cache por 30 dias, para nunca repetir a mesma consulta;
  - teto de consultas por execução (GEOCODING_LIMITE_POR_EXECUCAO).

Quando o endereço não resolve, o local recebe o centro da região administrativa
e fica marcado como coordenada_aproximada — melhor um ponto aproximado no mapa
do que um local invisível. Endereço que falha é marcado para não ser tentado
de novo em toda execução.

Usa urllib da biblioteca padrão: nenhuma dependência nova.
"""

import json
import logging
import time
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from ..constants import CENTROIDE_POR_REGIAO, Regiao, normalizar

logger = logging.getLogger("eventos.ingestao")

CAIXA_DF = (-16.10, -48.35, -15.45, -47.30)  # sul, oeste, norte, leste


class GeocodificacaoIndisponivel(Exception):
    pass


def _chave_cache(consulta):
    return f"geo:{normalizar(consulta)[:180]}"


def dentro_do_df(lat, lon):
    sul, oeste, norte, leste = CAIXA_DF
    return sul <= lat <= norte and oeste <= lon <= leste


def montar_consulta(local):
    partes = [local.nome]
    if local.endereco:
        partes.append(local.endereco)
    if local.regiao and local.regiao != Regiao.ONLINE:
        partes.append(local.get_regiao_display())
    partes.append(local.cidade or "Brasília")
    partes.append("Distrito Federal, Brasil")
    return ", ".join(p for p in partes if p)


def consultar(endereco, timeout=None):
    """Devolve (lat, lon) ou None. Resultado negativo também vai para o cache."""
    if not getattr(settings, "GEOCODING_ATIVO", True):
        raise GeocodificacaoIndisponivel("Geocodificação desligada nesta configuração.")

    chave = _chave_cache(endereco)
    guardado = cache.get(chave)
    if guardado is not None:
        return tuple(guardado) if guardado else None

    parametros = urllib.parse.urlencode(
        {
            "q": endereco,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "br",
            "viewbox": "-48.35,-15.45,-47.30,-16.10",
            "bounded": 1,
        }
    )
    url = f"{settings.GEOCODING_URL}?{parametros}"
    pedido = urllib.request.Request(
        url,
        headers={
            "User-Agent": settings.GEOCODING_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "pt-BR",
        },
    )

    try:
        with urllib.request.urlopen(
            pedido, timeout=timeout or settings.INGESTAO_HTTP_TIMEOUT
        ) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:
        logger.warning("Geocodificação falhou para %r: %s", endereco[:80], erro)
        raise GeocodificacaoIndisponivel(str(erro)) from erro

    if not dados:
        cache.set(chave, [], settings.GEOCODING_CACHE_SEGUNDOS)
        return None

    try:
        lat, lon = float(dados[0]["lat"]), float(dados[0]["lon"])
    except (KeyError, ValueError, IndexError):
        cache.set(chave, [], settings.GEOCODING_CACHE_SEGUNDOS)
        return None

    if not dentro_do_df(lat, lon):
        logger.info("Coordenada fora do DF descartada para %r", endereco[:80])
        cache.set(chave, [], settings.GEOCODING_CACHE_SEGUNDOS)
        return None

    cache.set(chave, [lat, lon], settings.GEOCODING_CACHE_SEGUNDOS)
    return lat, lon


def geocodificar_local(local, usar_rede=True):
    """Preenche latitude/longitude do local. Devolve 'exata', 'aproximada' ou 'falhou'."""
    if local.regiao == Regiao.ONLINE:
        local.geocodificacao_falhou = True
        local.save(update_fields=["geocodificacao_falhou"])
        return "falhou"

    coordenada = None
    if usar_rede:
        try:
            coordenada = consultar(montar_consulta(local))
        except GeocodificacaoIndisponivel:
            coordenada = None

    if coordenada:
        local.latitude, local.longitude = coordenada
        local.coordenada_aproximada = False
        resultado = "exata"
    else:
        centro = CENTROIDE_POR_REGIAO.get(local.regiao)
        if not centro:
            local.geocodificacao_falhou = True
            local.save(update_fields=["geocodificacao_falhou"])
            return "falhou"
        local.latitude, local.longitude = centro
        local.coordenada_aproximada = True
        resultado = "aproximada"

    local.geocodificado_em = timezone.now()
    local.geocodificacao_falhou = False
    local.atualizar_metro()
    local.save(
        update_fields=[
            "latitude", "longitude", "coordenada_aproximada", "geocodificado_em",
            "geocodificacao_falhou", "metro_proximo", "metro_distancia_m",
        ]
    )
    return resultado


def geocodificar_pendentes(limite=None, usar_rede=True, ao_processar=None):
    """Processa a fila respeitando a pausa entre chamadas."""
    from ..models import Evento, Local

    limite = limite or settings.GEOCODING_LIMITE_POR_EXECUCAO
    pausa = settings.GEOCODING_PAUSA_SEGUNDOS
    contagem = {"exata": 0, "aproximada": 0, "falhou": 0}

    pendentes = list(Local.objects.pendentes_de_geocodificacao()[:limite])
    for indice, local in enumerate(pendentes):
        if indice and usar_rede:
            time.sleep(pausa)
        resultado = geocodificar_local(local, usar_rede=usar_rede)
        contagem[resultado] += 1
        if ao_processar:
            ao_processar(local, resultado)
        # Propaga a coordenada para os eventos daquele local.
        Evento.objects.filter(local_ref=local).update(
            latitude=local.latitude, longitude=local.longitude
        )

    return contagem
