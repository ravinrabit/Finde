"""Conector do Mapa nas Nuvens — a cartografia cultural oficial do DF.

Por que esta é a fonte prioritária:
  - é do próprio GDF (Secretaria de Cultura), que orienta produtores a
    cadastrarem a programação lá;
  - roda sobre Mapas Culturais, software livre com API pública documentada;
  - traz georreferenciamento, que é justamente o que falta no Finde;
  - risco jurídico zero: dado público, uso previsto.

A API do Mapas Culturais expõe /api/<entidade>/find/ com @select, @files e
filtros por campo. O formato de resposta varia um pouco entre versões da
plataforma, então o parser aqui é defensivo: campo que não vier é ignorado, e
evento sem data é descartado em vez de receber data inventada.

ANTES DE CONFIAR NESTA FONTE, MEÇA:
    python manage.py medir_mapa_nas_nuvens
O comando diz quantos eventos futuros existem, quais campos vêm preenchidos e
qual a cobertura por região. Se o volume for baixo, a estratégia muda — não
construa infraestrutura em cima de uma fonte que você não mediu.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from ..constants import Regiao, normalizar
from .base import EventoImportado, garantir_aware
from .http import FonteIndisponivel, buscar_json

logger = logging.getLogger("eventos.ingestao")

FONTE = "mapa-df"

CAMPOS = (
    "id,name,shortDescription,longDescription,type,terms,singleUrl,"
    "occurrences.{rule,space.{id,name,endereco,location,En_Nome_Logradouro,"
    "En_Num,En_Bairro,En_CEP,En_Municipio}},owner.{id,name},"
    "@files.avatar.transform(header),createTimestamp"
)

# As linguagens do Mapas Culturais não são as categorias do Finde.
MAPA_CATEGORIAS = {
    "musica": "musica", "musica popular": "musica", "musica erudita": "musica",
    "artes cenicas": "teatro", "teatro": "teatro", "danca": "arte",
    "circo": "arte", "artes circenses": "arte", "artes visuais": "arte",
    "artes integradas": "cultura", "audiovisual": "cinema", "cinema": "cinema",
    "livro e literatura": "cultura", "cultura popular": "cultura",
    "cultura tradicional": "cultura", "cultura indigena": "cultura",
    "cultura digital": "tecnologia", "hip hop": "musica",
    "exposicao": "exposicoes", "curso ou oficina": "workshops",
    "palestra, debate ou encontro": "educacao", "patrimonio": "cultura",
    "moda": "arte", "gastronomia": "gastronomia", "radio": "cultura",
}


def _url(caminho):
    base = settings.MAPA_NAS_NUVENS_URL.rstrip("/")
    return f"{base}{caminho}"


def _texto(valor):
    return valor.strip() if isinstance(valor, str) else ""


def _ler_data(valor):
    if not valor:
        return None
    if isinstance(valor, dict):
        valor = valor.get("date") or valor.get("value") or ""
    texto = str(valor).strip().replace("T", " ").split(".")[0]
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return garantir_aware(datetime.strptime(texto, formato))
        except ValueError:
            continue
    return None


def _hora(valor, padrao="20:00"):
    texto = _texto(valor) or padrao
    return texto[:5] if len(texto) >= 5 else padrao


def _coordenadas(space):
    location = (space or {}).get("location") or {}
    try:
        return float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


def _regiao(space):
    """Casa o bairro/município do espaço com uma RA do DF."""
    if not space:
        return ""
    alvo = " " + normalizar(
        " ".join(
            str(space.get(c) or "")
            for c in ("En_Bairro", "En_Municipio", "endereco", "name")
        )
    ) + " "
    for r in Regiao:
        if r == Regiao.ONLINE:
            continue
        rotulo = normalizar(r.label).split("/")[0].strip()
        if rotulo and f" {rotulo} " in alvo:
            return r.value
    return ""


def _endereco(space):
    if not space:
        return ""
    partes = [
        space.get("En_Nome_Logradouro"),
        space.get("En_Num"),
        space.get("En_Bairro"),
    ]
    texto = ", ".join(_texto(p) for p in partes if _texto(p))
    return texto or _texto(space.get("endereco"))


def _categoria(bruto):
    termos = (bruto.get("terms") or {}).get("linguagem") or []
    if isinstance(termos, str):
        termos = [termos]
    for termo in termos:
        destino = MAPA_CATEGORIAS.get(normalizar(termo))
        if destino:
            return destino
    return ""


def _imagem(bruto):
    arquivos = bruto.get("@files:avatar.header") or bruto.get("@files:avatar") or {}
    if isinstance(arquivos, dict):
        return _texto(arquivos.get("url"))
    if isinstance(arquivos, list) and arquivos:
        return _texto((arquivos[0] or {}).get("url"))
    return ""


def _ocorrencias(bruto, desde):
    """Cada ocorrência futura vira um evento próprio.

    O Mapas Culturais guarda a recorrência numa regra JSON. Enquanto o Finde
    não tem model de sessão, cada data futura entra como um registro distinto,
    com id_externo próprio, o que mantém a idempotência.
    """
    saida = []
    for ocorrencia in bruto.get("occurrences") or []:
        regra = ocorrencia.get("rule") or {}
        if isinstance(regra, str):
            continue
        inicio = _ler_data(regra.get("startsOn"))
        if not inicio:
            continue
        hora_inicio = _hora(regra.get("startsAt"), "20:00")
        hora_fim = _hora(regra.get("endsAt"), "")
        try:
            h, m = (int(x) for x in hora_inicio.split(":")[:2])
            inicio = inicio.replace(hour=h, minute=m)
        except (ValueError, TypeError):
            pass
        if inicio < desde:
            continue
        fim = None
        if hora_fim:
            try:
                h, m = (int(x) for x in hora_fim.split(":")[:2])
                fim = inicio.replace(hour=h, minute=m)
                if fim < inicio:
                    fim = None
            except (ValueError, TypeError):
                fim = None
        saida.append((inicio, fim, ocorrencia.get("space") or {}))
    return saida


def para_importados(bruto, desde):
    nome = _texto(bruto.get("name"))
    if not nome:
        return []

    descricao = _texto(bruto.get("longDescription")) or _texto(bruto.get("shortDescription"))
    imagem = _imagem(bruto)
    organizador = _texto((bruto.get("owner") or {}).get("name"))
    link = _texto(bruto.get("singleUrl")) or _url(f"/evento/{bruto.get('id')}/")
    categoria = _categoria(bruto)

    achados = []
    for indice, (inicio, fim, space) in enumerate(_ocorrencias(bruto, desde)):
        lat, lon = _coordenadas(space)
        achados.append(
            EventoImportado(
                id_externo=f"mnn:{bruto.get('id')}:{inicio:%Y%m%d%H%M}"[:120],
                nome=nome[:300],
                data=inicio,
                data_fim=fim,
                local=_texto(space.get("name"))[:300] or "A confirmar",
                endereco=_endereco(space)[:300],
                descricao=descricao[:4000],
                categoria=categoria,
                organizador=organizador[:200],
                imagem_url=imagem[:600],
                link_original=link[:600],
                regiao=_regiao(space),
                latitude=lat,
                longitude=lon,
            )
        )
    return achados


def buscar_bruto(limite=200, desde=None):
    """Consulta crua da API. Usada pelo conector e pelo comando de medição."""
    desde = desde or timezone.localdate()
    parametros = (
        f"@select={CAMPOS}"
        f"&@order=createTimestamp DESC"
        f"&@limit={int(limite)}"
        f"&occurrences.rule.startsOn=GTE({desde:%Y-%m-%d})"
    )
    url = _url(f"/api/event/find/?{parametros}")
    dados = buscar_json(url)
    if not isinstance(dados, list):
        raise FonteIndisponivel("A API não devolveu uma lista de eventos.")
    return dados


def coletar(limite=200, **_):
    desde = timezone.now()
    try:
        brutos = buscar_bruto(limite=limite, desde=desde.date())
    except FonteIndisponivel as erro:
        logger.error("Mapa nas Nuvens indisponível: %s", erro)
        return []

    achados = []
    for bruto in brutos:
        achados.extend(para_importados(bruto, desde))
    achados.sort(key=lambda e: e.data)
    logger.info("Mapa nas Nuvens: %d ocorrência(s) futura(s)", len(achados))
    return achados[:limite]
