from django.db.models import Count, Q
from django.utils import timezone

from ..models import Evento, Ingresso, Local, Produtor

TAMANHO_PREVIA = 5


def inicio_da_semana(referencia=None):
    agora = referencia or timezone.now()
    inicio = agora - timezone.timedelta(days=agora.weekday())
    return inicio.replace(hour=0, minute=0, second=0, microsecond=0)


def estatisticas_gerais():
    agora = timezone.now()
    semana = inicio_da_semana(agora)

    por_status = dict(
        Evento.objects.values_list("status").annotate(total=Count("id")).order_by()
    )

    return {
        "eventos_pendentes": por_status.get(Evento.Status.PENDENTE, 0),
        "eventos_publicados": por_status.get(Evento.Status.PUBLICADO, 0),
        "eventos_rejeitados": por_status.get(Evento.Status.REJEITADO, 0),
        "eventos_arquivados": por_status.get(Evento.Status.ARQUIVADO, 0),
        "eventos_criados_na_semana": Evento.objects.filter(criado_em__gte=semana).count(),
        "eventos_acontecendo_hoje": Evento.objects.filter(data__date=timezone.localdate()).count(),
        "total_produtores": Produtor.objects.count(),
        "produtores_nao_verificados": Produtor.objects.filter(verificado=False).count(),
        "total_locais": Local.objects.count(),
        "locais_sem_coordenada": Local.objects.filter(latitude__isnull=True).count(),
        "ingressos_confirmados_na_semana": Ingresso.objects.filter(
            status=Ingresso.Status.CONFIRMADO, data_compra__gte=semana
        ).count(),
    }


def fila_de_moderacao(status=None, busca=""):
    eventos = Evento.objects.select_related("local_ref", "produtor", "criado_por")

    if status:
        eventos = eventos.filter(status=status)
    if busca:
        eventos = eventos.filter(
            Q(nome__icontains=busca) | Q(produtor__nome__icontains=busca)
        )

    ordenacao = "criado_em" if status == Evento.Status.PENDENTE else "-criado_em"
    return eventos.order_by(ordenacao)


def previa_pendentes():
    return fila_de_moderacao(status=Evento.Status.PENDENTE)[:TAMANHO_PREVIA]


def produtores_para_revisao(apenas_nao_verificados=False, busca=""):
    produtores = Produtor.objects.select_related("user").annotate(
        total_eventos=Count("eventos")
    )

    if apenas_nao_verificados:
        produtores = produtores.filter(verificado=False)
    if busca:
        produtores = produtores.filter(nome__icontains=busca)

    return produtores.order_by("-criado_em")


def previa_produtores_pendentes():
    return produtores_para_revisao(apenas_nao_verificados=True)[:TAMANHO_PREVIA]
