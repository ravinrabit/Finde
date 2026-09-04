"""Reserva de ingressos.

A regra estava dentro da view, lendo request.POST direto, sem transação e sem
nenhum limite além de "no máximo 10 por requisição" — o que não impedia
ninguém de repetir a requisição mil vezes.

Aqui a reserva vira uma operação atômica e testável, com o desenho já pronto
para a etapa seguinte (pedido -> pagamento -> webhook -> confirmação), sem
implementar pagamento antes da infraestrutura de reserva existir.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q

from ..models import Evento, Ingresso

LIMITE_ABSOLUTO_POR_PEDIDO = 10


class ReservaInvalida(Exception):
    """Motivo de negócio para a reserva não acontecer. A view vira mensagem."""


@dataclass(frozen=True)
class Reserva:
    evento: Evento
    ingressos: list
    tipo: str
    valor_unitario: object

    @property
    def quantidade(self):
        return len(self.ingressos)

    @property
    def total(self):
        return self.valor_unitario * self.quantidade


def normalizar_tipo(bruto):
    return bruto if bruto in Ingresso.Tipo.values else Ingresso.Tipo.INTEIRA


def normalizar_quantidade(bruto, maximo=LIMITE_ABSOLUTO_POR_PEDIDO):
    try:
        quantidade = int(bruto)
    except (TypeError, ValueError):
        quantidade = 1
    return max(1, min(quantidade, maximo))


def ingressos_do_usuario(evento, usuario):
    return (
        Ingresso.objects.filter(evento=evento, usuario=usuario)
        .exclude(status=Ingresso.Status.CANCELADO)
        .count()
    )


def vagas_restantes(evento):
    """None = evento sem capacidade definida, ou seja, sem limite."""
    if evento.capacidade is None:
        return None
    ocupadas = (
        Ingresso.objects.filter(evento=evento)
        .exclude(status=Ingresso.Status.CANCELADO)
        .count()
    )
    return max(0, evento.capacidade - ocupadas)


@transaction.atomic
def reservar(usuario, evento, tipo, quantidade):
    """Cria os ingressos ou levanta ReservaInvalida. Tudo ou nada.

    O select_for_update trava a linha do evento até o fim da transação: duas
    reservas simultâneas para a última vaga entram em fila em vez de as duas
    passarem pela checagem de capacidade.

    Em SQLite não há lock de linha, mas o backend já roda em modo IMMEDIATE,
    que serializa a escrita — o efeito prático é o mesmo.
    """
    evento = Evento.objects.select_for_update().get(pk=evento.pk)

    if evento.status != Evento.Status.PUBLICADO:
        raise ReservaInvalida("Este evento não está disponível para reserva.")
    if evento.ja_aconteceu:
        raise ReservaInvalida("Este evento já aconteceu.")

    tipo = normalizar_tipo(tipo)
    quantidade = normalizar_quantidade(quantidade)

    limite_usuario = evento.limite_por_usuario or LIMITE_ABSOLUTO_POR_PEDIDO
    ja_tem = ingressos_do_usuario(evento, usuario)
    if ja_tem >= limite_usuario:
        raise ReservaInvalida(
            f"Você já reservou o máximo de {limite_usuario} ingresso(s) para este evento."
        )
    if ja_tem + quantidade > limite_usuario:
        disponivel = limite_usuario - ja_tem
        raise ReservaInvalida(
            f"Você pode reservar mais {disponivel} ingresso(s) para este evento."
        )

    restantes = vagas_restantes(evento)
    if restantes is not None:
        if restantes == 0:
            raise ReservaInvalida("Este evento está esgotado.")
        if quantidade > restantes:
            raise ReservaInvalida(
                f"Restam apenas {restantes} ingresso(s) para este evento."
            )

    valor = evento.valor_para(tipo)
    ingressos = Ingresso.objects.bulk_create(
        [
            Ingresso(usuario=usuario, evento=evento, tipo=tipo, valor=valor)
            for _ in range(quantidade)
        ]
    )
    return Reserva(evento=evento, ingressos=ingressos, tipo=tipo, valor_unitario=valor)


@transaction.atomic
def cancelar(ingresso):
    from django.utils import timezone

    if not ingresso.pode_cancelar:
        raise ReservaInvalida("Este ingresso não pode mais ser cancelado.")
    ingresso.status = Ingresso.Status.CANCELADO
    ingresso.cancelado_em = timezone.now()
    ingresso.save(update_fields=["status", "cancelado_em"])
    return ingresso


@transaction.atomic
def marcar_utilizado(ingresso):
    """Check-in na porta. O status UTILIZADO existia no modelo e nunca era usado."""
    from django.utils import timezone

    if ingresso.status == Ingresso.Status.CANCELADO:
        raise ReservaInvalida("Este ingresso foi cancelado.")
    if ingresso.status == Ingresso.Status.UTILIZADO:
        raise ReservaInvalida("Este ingresso já foi utilizado.")
    ingresso.status = Ingresso.Status.UTILIZADO
    ingresso.utilizado_em = timezone.now()
    ingresso.save(update_fields=["status", "utilizado_em"])
    return ingresso


def resumo_de_ocupacao(eventos):
    """Contagem de confirmados por evento numa consulta só, para o painel."""
    return {
        linha["pk"]: linha["confirmados"]
        for linha in eventos.annotate(
            confirmados=Count("ingressos", filter=~Q(ingressos__status=Ingresso.Status.CANCELADO))
        ).values("pk", "confirmados")
    }
