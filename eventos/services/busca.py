from django.db import connection
from django.db.models import Q

from ..constants import normalizar

MIN_TERMO = 2
MAX_TERMOS = 8


def termos_de(consulta):
    return [t for t in normalizar(consulta).split() if len(t) >= MIN_TERMO][:MAX_TERMOS]


def _filtro_por_termos(termos, qualquer):
    filtro = Q()
    for termo in termos:
        condicao = Q(busca_texto__contains=termo)
        filtro = (filtro | condicao) if qualquer else (filtro & condicao)
    return filtro


def aplicar(queryset, consulta, qualquer=False):
    """qualquer=True faz OR entre os termos, em vez de exigir todos — usado
    para consultas em linguagem natural (assistente de IA), onde exigir que
    palavras como "quais"/"tem" apareçam no texto do evento nunca bate."""
    termos = termos_de(consulta)
    if not termos:
        return queryset

    if connection.vendor == "postgresql":
        return _postgres(queryset, consulta, termos, qualquer)

    return queryset.filter(_filtro_por_termos(termos, qualquer))


def _postgres(queryset, consulta, termos, qualquer):
    try:
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
    except ImportError:  # pragma: no cover
        return queryset.filter(_filtro_por_termos(termos, qualquer))

    vetor = (
        SearchVector("nome", weight="A", config="portuguese")
        + SearchVector("resumo", weight="B", config="portuguese")
        + SearchVector("local", weight="B", config="portuguese")
        + SearchVector("organizador", weight="C", config="portuguese")
        + SearchVector("descricao", weight="D", config="portuguese")
    )
    if qualquer:
        # Consulta em linguagem natural: OR entre os termos individuais, sem
        # depender de sintaxe crua de tsquery (os termos já vêm sanitizados,
        # mas SearchQuery encadeado evita qualquer risco de parsing).
        pergunta = None
        for termo in termos:
            parte = SearchQuery(termo, config="portuguese")
            pergunta = parte if pergunta is None else (pergunta | parte)
    else:
        pergunta = SearchQuery(consulta, config="portuguese", search_type="websearch")

    like = _filtro_por_termos(termos, qualquer)

    return (
        queryset.annotate(vetor_busca=vetor, relevancia=SearchRank(vetor, pergunta))
        .filter(Q(vetor_busca=pergunta) | like)
        .distinct()
    )


def ordenar_por_relevancia(queryset):
    if connection.vendor == "postgresql" and "relevancia" in queryset.query.annotations:
        return queryset.order_by("-relevancia", "data")
    return queryset
