from django.utils import timezone

from .. import emails
from ..models import Evento


def publicar(evento, request=None):
    if evento.status == Evento.Status.PUBLICADO:
        return False
    evento.status = Evento.Status.PUBLICADO
    evento.publicado_em = evento.publicado_em or timezone.now()
    evento.motivo_rejeicao = ""
    evento.save(update_fields=["status", "publicado_em", "motivo_rejeicao"])
    url = request.build_absolute_uri(evento.get_absolute_url()) if request else ""
    emails.evento_publicado(evento, url)
    return True


def rejeitar(evento, motivo="", request=None):
    evento.status = Evento.Status.REJEITADO
    evento.publicado_em = None
    if motivo:
        evento.motivo_rejeicao = motivo
    evento.save(update_fields=["status", "publicado_em", "motivo_rejeicao"])
    url = request.build_absolute_uri(evento.get_absolute_url()) if request else ""
    emails.evento_rejeitado(evento, motivo=evento.motivo_rejeicao, url_absoluta=url)
    return True


def arquivar(evento):
    evento.status = Evento.Status.ARQUIVADO
    evento.save(update_fields=["status"])
    return True


def verificar_produtor(produtor, verificado=True):
    produtor.verificado = verificado
    produtor.save(update_fields=["verificado"])
    return produtor
