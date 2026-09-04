"""Busca textual tolerante a acento e caixa.

A coluna Evento.busca_texto guarda nome, resumo, descrição, local, endereço,
organizador, cidade, categoria e região — tudo em minúsculas e sem acento.
Buscar nela resolve, em qualquer banco:

    rock / Rock / ROCK        -> mesma consulta
    cinema / cinéma           -> mesma consulta
    brasilia / Brasília       -> mesma consulta

Antes, a busca fazia icontains em cinco colunas com OR, o que varre a tabela
inteira e ainda erra em acento.

No PostgreSQL, além disso, existe full-text em português com ranking. A
migration 0009 cria o índice GIN de trigrama que faz o LIKE usar índice.
"""

from django.db import connection
from django.db.models import Q

from ..constants import normalizar

MIN_TERMO = 2
MAX_TERMOS = 8


def termos_de(consulta):
    """Quebra a consulta em termos normalizados úteis."""
    return [t for t in normalizar(consulta).split() if len(t) >= MIN_TERMO][:MAX_TERMOS]


def aplicar(queryset, consulta):
    """Filtra o queryset pelos termos. Sem consulta, devolve intacto.

    Todos os termos precisam aparecer (AND), o que dá resultados muito mais
    relevantes do que OR quando alguém busca "show rock ceilandia".
    """
    termos = termos_de(consulta)
    if not termos:
        return queryset

    if connection.vendor == "postgresql":
        return _postgres(queryset, consulta, termos)

    filtro = Q()
    for termo in termos:
        filtro &= Q(busca_texto__contains=termo)
    return queryset.filter(filtro)


def _postgres(queryset, consulta, termos):
    """Full-text em português, com o LIKE normalizado como rede de segurança.

    O full-text acerta plural e radical ("festivais" acha "festival"); o LIKE
    pega o que o dicionário não cobre (nomes próprios, siglas, parte de palavra).
    """
    try:
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    except ImportError:  # pragma: no cover
        filtro = Q()
        for termo in termos:
            filtro &= Q(busca_texto__contains=termo)
        return queryset.filter(filtro)

    vetor = (
        SearchVector("nome", weight="A", config="portuguese")
        + SearchVector("resumo", weight="B", config="portuguese")
        + SearchVector("local", weight="B", config="portuguese")
        + SearchVector("organizador", weight="C", config="portuguese")
        + SearchVector("descricao", weight="D", config="portuguese")
    )
    pergunta = SearchQuery(consulta, config="portuguese", search_type="websearch")

    like = Q()
    for termo in termos:
        like &= Q(busca_texto__contains=termo)

    return (
        queryset.annotate(vetor_busca=vetor, relevancia=SearchRank(vetor, pergunta))
        .filter(Q(vetor_busca=pergunta) | like)
        .distinct()
    )


def ordenar_por_relevancia(queryset):
    """Só faz sentido depois de aplicar() no PostgreSQL."""
    if connection.vendor == "postgresql" and "relevancia" in queryset.query.annotations:
        return queryset.order_by("-relevancia", "data")
    return queryset
