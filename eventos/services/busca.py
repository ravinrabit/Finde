from django.db import connection
from django.db.models import Q

from ..constants import normalizar

MIN_TERMO = 2
MAX_TERMOS = 8


def termos_de(consulta):
    return [t for t in normalizar(consulta).split() if len(t) >= MIN_TERMO][:MAX_TERMOS]


def aplicar(queryset, consulta):
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
    if connection.vendor == "postgresql" and "relevancia" in queryset.query.annotations:
        return queryset.order_by("-relevancia", "data")
    return queryset
