import json

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..constants import ICONE_PADRAO, ICONE_POR_CATEGORIA
from ..models import formatar_reais

register = template.Library()

# json.dumps não escapa <, > e &, então um nome de evento contendo "</script>"
# fecharia a tag e injetaria HTML. Mesmo tratamento do filtro json_script do Django.
ESCAPES_JSON = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}

MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

# Traçados de 24x24 usados nos ícones de categoria e de interface.
TRACADOS = {
    "microfone": "M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3ZM5 10v1a7 7 0 0 0 14 0v-1M12 18v4",
    "taca": "M8 3h8l-1 6a3 3 0 0 1-6 0L8 3ZM12 12v8M8 21h8",
    "nota": "M9 18V5l10-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM19 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
    "estrela": "m12 3 2.6 5.6 6.1.8-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6L3.3 9.4l6.1-.8L12 3Z",
    "mascara": "M4 5h16v6a8 8 0 0 1-16 0V5ZM9 9h.01M15 9h.01M9 14c1.8 1.4 4.2 1.4 6 0",
    "claquete": "M3 8h18v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8ZM3 8l2-4h14l-2 4M8 4 6 8M13 4l-2 4",
    "livro": "M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3V4ZM4 17a3 3 0 0 1 3-3h11",
    "prato": "M12 3v10M9 3v5a3 3 0 0 0 6 0V3M5 21h14M7 13h10l-1 8H8l-1-8Z",
    "bola": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM12 3v6M3.6 8.5 9 12M20.4 8.5 15 12M6.5 19.5 9 12M17.5 19.5 15 12",
    "chip": "M7 7h10v10H7V7ZM4 10h3M4 14h3M17 10h3M17 14h3M10 4v3M14 4v3M10 17v3M14 17v3",
    "pasta": "M3 7h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7ZM3 12h18",
    "pessoas": "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 20a6 6 0 0 1 12 0M17 11a3 3 0 1 0 0-6M16 14a6 6 0 0 1 6 6",
    "ferramenta": "M14 6a4 4 0 0 0 5.5 5.2L21 13l-8 8-2-2 1.8-1.5A4 4 0 0 0 7.5 12L4 8.5 8.5 4 12 7.5",
    "quadro": "M3 4h18v14H3V4ZM3 14l5-5 4 4 3-3 6 6M9 9h.01M12 18v3M9 21h6",
    "pincel": "M4 20c0-3 2-4 4-4s3 1 3 3-1 3-4 3H4v-2ZM11 16 20 5a2 2 0 0 0-3-3l-9 11",
    "balao": "M12 3a5 5 0 0 1 5 5c0 4-5 8-5 8s-5-4-5-8a5 5 0 0 1 5-5ZM12 16v3M10 21h4",
    "vela": "M12 3s3 3 3 5a3 3 0 0 1-6 0c0-2 3-5 3-5ZM9 11h6v10H9V11Z",
    "capelo": "m12 4 10 5-10 5L2 9l10-5ZM6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5",
    "arvore": "M12 3 6 12h3l-3 5h12l-3-5h3L12 3ZM12 17v4",
    "ingresso": "M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2 2 2 0 0 0 0 4 2 2 0 0 1 0 4H6a2 2 0 0 1-2-2 2 2 0 0 0 0-4ZM14 6v12",

    "coracao": "M12 20s-7-4.4-7-9a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 4.6-7 9-7 9Z",
    "pino": "M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11ZM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
    "calendario": "M4 6h16v14H4V6ZM8 3v5M16 3v5M4 11h16",
    "relogio": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3.5 2",
    "busca": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM21 21l-4.2-4.2",
    "seta-esquerda": "M19 12H5M11 18l-6-6 6-6",
    "compartilhar": "M14 9V5l7 7-7 7v-4.1C9.4 14.5 6.3 15.9 4 19c.6-4.9 3.5-8.6 10-10Z",
    "dinheiro": "M12 3v18M16.5 7.5A4 4 0 0 0 13 6h-2a3 3 0 0 0 0 6h2a3 3 0 0 1 0 6h-2a4 4 0 0 1-3.5-1.5",
    "globo": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM3.5 9h17M3.5 15h17M12 3c2.4 2.4 3.6 5.4 3.6 9S14.4 18.6 12 21c-2.4-2.4-3.6-5.4-3.6-9S9.6 5.4 12 3Z",
    "alerta": "M12 4 2.5 20h19L12 4ZM12 10v4M12 17.5h.01",
    "confirmado": "M20 6 9 17l-5-5",
    "vazio": "M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8ZM4 11h16M9 15h2",
}


@register.simple_tag
def icone(nome, tamanho=20, classe=""):
    tracado = TRACADOS.get(nome)
    if not tracado:
        return ""
    return format_html(
        '<svg class="icone {}" width="{}" height="{}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="{}"/></svg>',
        classe, tamanho, tamanho, tracado,
    )


@register.simple_tag
def icone_categoria(categoria, tamanho=20, classe=""):
    return icone(ICONE_POR_CATEGORIA.get(categoria, ICONE_PADRAO), tamanho, classe)


@register.filter
def reais(valor):
    if valor is None:
        return "Valor a definir"
    return "Gratuito" if valor == 0 else formatar_reais(valor)


@register.filter
def dia_curto(data):
    local = timezone.localtime(data)
    return f"{local.day:02d}"


@register.filter
def mes_curto(data):
    return MESES_CURTOS[timezone.localtime(data).month - 1]


@register.filter
def quando(evento):
    """Rótulo humano: 'Hoje, 20h', 'Amanhã, 19h30', 'sáb 12 set, 21h'."""
    inicio = timezone.localtime(evento.data)
    hora = f"{inicio.hour}h" if inicio.minute == 0 else f"{inicio.hour}h{inicio.minute:02d}"
    dias = evento.dias_ate_comecar

    if evento.acontecendo_agora:
        return "Acontecendo agora"
    if dias == 0:
        return f"Hoje, {hora}"
    if dias == 1:
        return f"Amanhã, {hora}"

    rotulo = f"{DIAS_SEMANA[inicio.weekday()]} {inicio.day} {MESES_CURTOS[inicio.month - 1]}"
    if inicio.year != timezone.localdate().year:
        rotulo += f" {inicio.year}"
    return f"{rotulo}, {hora}"


@register.filter
def intervalo_datas(evento):
    inicio = timezone.localtime(evento.data)
    texto = f"{inicio.day} de {_mes_extenso(inicio.month)} de {inicio.year}, {inicio:%H:%M}"
    if evento.data_fim:
        fim = timezone.localtime(evento.data_fim)
        if fim.date() == inicio.date():
            return f"{texto} às {fim:%H:%M}"
        return f"{texto} — {fim.day} de {_mes_extenso(fim.month)}, {fim:%H:%M}"
    return texto


def _mes_extenso(numero):
    nomes = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return nomes[numero - 1]


@register.simple_tag(takes_context=True)
def dados_estruturados(context, evento):
    """JSON-LD schema.org/Event — melhora o resultado do evento na busca do Google."""
    pedido = context["request"]
    dados = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": evento.nome,
        "startDate": evento.data.isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": (
            "https://schema.org/OnlineEventAttendanceMode"
            if evento.modalidade == "online"
            else "https://schema.org/OfflineEventAttendanceMode"
        ),
        "url": pedido.build_absolute_uri(evento.get_absolute_url()),
        "description": evento.resumo or evento.descricao[:300],
    }
    if evento.data_fim:
        dados["endDate"] = evento.data_fim.isoformat()
    if evento.imagem_exibicao:
        dados["image"] = pedido.build_absolute_uri(evento.imagem_exibicao)
    if evento.modalidade != "online":
        dados["location"] = {
            "@type": "Place",
            "name": evento.local,
            "address": {
                "@type": "PostalAddress",
                "streetAddress": evento.endereco,
                "addressLocality": evento.cidade,
                "addressRegion": "DF",
                "addressCountry": "BR",
            },
        }
    if evento.modalidade != "online" and evento.tem_coordenadas:
        dados["location"]["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": float(evento.latitude),
            "longitude": float(evento.longitude),
        }
    if evento.organizador_nome:
        organizador = {"@type": "Organization", "name": evento.organizador_nome}
        if evento.produtor_id:
            organizador["url"] = pedido.build_absolute_uri(evento.produtor.get_absolute_url())
        dados["organizer"] = organizador
    if evento.gratuito or evento.preco is not None:
        dados["offers"] = {
            "@type": "Offer",
            "price": str(evento.preco or 0),
            "priceCurrency": "BRL",
            "availability": (
                "https://schema.org/SoldOut" if evento.esgotado
                else "https://schema.org/InStock"
            ),
            "validFrom": (evento.publicado_em or evento.data).isoformat(),
            "url": pedido.build_absolute_uri(evento.get_absolute_url()),
        }
    return mark_safe(json.dumps(dados, ensure_ascii=False).translate(ESCAPES_JSON))


# ---------------------------------------------------------------------------
# Imagens responsivas (FASE 10)
# ---------------------------------------------------------------------------

@register.filter
def srcset(campo_imagem):
    """srcset das variantes WebP geradas no upload.

    Vazio quando não há variante: o template então usa só o original, e nada
    quebra em instalação que ainda não rodou `gerar_variantes_imagem`.
    """
    try:
        from ..services.imagens import srcset as montar

        return montar(campo_imagem)
    except Exception:
        return ""


@register.simple_tag
def capa(evento, tamanhos="(max-width: 640px) 100vw, 400px", classe="", carregamento="lazy"):
    """<img> da capa com srcset, dimensões e lazy loading.

    Reúne num só lugar o que estava repetido em cada template, e evita que um
    card esqueça de declarar width/height (o que causa salto de layout).
    """
    url = evento.imagem_exibicao
    if not url:
        return ""
    conjunto = srcset(evento.imagem) if evento.imagem else ""
    atributos = [
        format_html('src="{}"', url),
        format_html('alt="{}"', evento.nome),
        format_html('class="{}"', classe),
        format_html('loading="{}"', carregamento),
        'decoding="async"',
        'width="800"',
        'height="500"',
    ]
    if conjunto:
        atributos.append(format_html('srcset="{}"', conjunto))
        atributos.append(format_html('sizes="{}"', tamanhos))
    return mark_safe("<img " + " ".join(str(a) for a in atributos) + ">")


# ---------------------------------------------------------------------------
# Geolocalização (FASE 5/16)
# ---------------------------------------------------------------------------

@register.filter
def distancia(valor):
    """0,4 km / 2,7 km / 15 km — precisão proporcional ao número."""
    if valor is None:
        return ""
    if valor < 1:
        return f"{int(round(valor * 1000))} m"
    if valor < 10:
        return f"{valor:.1f}".replace(".", ",") + " km"
    return f"{int(round(valor))} km"


@register.filter
def metros(valor):
    if valor is None:
        return ""
    if valor < 1000:
        return f"{valor} m"
    return f"{valor / 1000:.1f}".replace(".", ",") + " km"


@register.simple_tag(takes_context=True)
def querystring_sem(context, *chaves, **novos):
    """Reconstrói a querystring removendo chaves e aplicando novos valores.

    Usada nos chips de filtro ("remover este filtro") e na paginação. Sempre
    devolve começando com "?" ou string vazia — nunca um "?" solto, que era a
    origem do "??page=2" que quebrava a paginação.
    """
    pedido = context.get("request")
    if pedido is None:
        return ""
    parametros = pedido.GET.copy()
    for chave in chaves:
        parametros.pop(chave, None)
    for chave, valor in novos.items():
        if valor in (None, ""):
            parametros.pop(chave, None)
        else:
            parametros[chave] = valor
    if "page" not in novos:
        # Mudar de filtro sempre volta para a primeira página; senão a pessoa
        # cai numa página 7 que não existe mais no resultado novo.
        parametros.pop("page", None)
    codificada = parametros.urlencode()
    return f"?{codificada}" if codificada else ""


@register.simple_tag(takes_context=True)
def querystring_pagina(context, numero):
    """Link de paginação preservando todos os filtros atuais."""
    pedido = context.get("request")
    if pedido is None:
        return f"?page={numero}"
    parametros = pedido.GET.copy()
    parametros["page"] = numero
    return f"?{parametros.urlencode()}"


@register.simple_tag(takes_context=True)
def remover_valor(context, chave, valor):
    """Tira UM valor de um filtro de múltipla escolha (ex.: um dos acessos)."""
    pedido = context.get("request")
    if pedido is None:
        return ""
    parametros = pedido.GET.copy()
    restantes = [v for v in parametros.getlist(chave) if v != str(valor)]
    parametros.setlist(chave, restantes)
    parametros.pop("page", None)
    codificada = parametros.urlencode()
    return f"?{codificada}" if codificada else ""
