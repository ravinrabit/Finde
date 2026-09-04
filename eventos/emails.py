"""E-mails transacionais.

A interface já prometia "Avisaremos assim que for publicado" e nada era
enviado. Cada função aqui monta um e-mail em texto puro a partir de um template
e nunca deixa uma falha de SMTP derrubar a requisição do usuário: se o envio
falhar, registra no log e segue.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger("eventos")


def _enviar(assunto, template, contexto, destinatarios):
    destinatarios = [e for e in destinatarios if e]
    if not destinatarios:
        return False
    contexto = {
        "SITE_NOME": settings.SITE_NOME,
        "SITE_DOMINIO": settings.SITE_DOMINIO,
        "EMAIL_CONTATO": settings.EMAIL_CONTATO,
        **contexto,
    }
    try:
        corpo = render_to_string(template, contexto)
        send_mail(
            f"[{settings.SITE_NOME}] {assunto}",
            corpo,
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            fail_silently=False,
        )
        return True
    except Exception as erro:
        logger.error("Falha ao enviar '%s' para %s: %s", assunto, destinatarios, erro)
        return False


def _email_do_evento(evento):
    alvos = []
    if evento.criado_por_id and evento.criado_por.email:
        alvos.append(evento.criado_por.email)
    if evento.produtor_id and evento.produtor.email:
        alvos.append(evento.produtor.email)
    return alvos


# -------------------- produtor --------------------

def evento_recebido(evento, url_absoluta=""):
    return _enviar(
        f"Recebemos seu evento: {evento.nome}",
        "emails/evento-recebido.txt",
        {"evento": evento, "url": url_absoluta},
        _email_do_evento(evento),
    )


def evento_publicado(evento, url_absoluta=""):
    return _enviar(
        f"Seu evento está no ar: {evento.nome}",
        "emails/evento-publicado.txt",
        {"evento": evento, "url": url_absoluta},
        _email_do_evento(evento),
    )


def evento_rejeitado(evento, motivo="", url_absoluta=""):
    return _enviar(
        f"Seu evento precisa de ajustes: {evento.nome}",
        "emails/evento-rejeitado.txt",
        {"evento": evento, "motivo": motivo or evento.motivo_rejeicao, "url": url_absoluta},
        _email_do_evento(evento),
    )


def evento_voltou_para_revisao(evento, campos, url_absoluta=""):
    return _enviar(
        f"Seu evento voltou para revisão: {evento.nome}",
        "emails/evento-revisao.txt",
        {"evento": evento, "campos": campos, "url": url_absoluta},
        _email_do_evento(evento),
    )


# -------------------- usuário --------------------

def reserva_confirmada(reserva, url_absoluta=""):
    usuario = reserva.ingressos[0].usuario
    return _enviar(
        f"Reserva confirmada: {reserva.evento.nome}",
        "emails/reserva-confirmada.txt",
        {"reserva": reserva, "evento": reserva.evento, "usuario": usuario, "url": url_absoluta},
        [usuario.email],
    )


def reserva_cancelada(ingresso, url_absoluta=""):
    return _enviar(
        f"Reserva cancelada: {ingresso.evento.nome}",
        "emails/reserva-cancelada.txt",
        {"ingresso": ingresso, "evento": ingresso.evento, "url": url_absoluta},
        [ingresso.usuario.email],
    )


def lembrete_de_evento(usuario, evento, ingressos, url_absoluta=""):
    return _enviar(
        f"Amanhã: {evento.nome}",
        "emails/lembrete.txt",
        {"evento": evento, "ingressos": ingressos, "usuario": usuario, "url": url_absoluta},
        [usuario.email],
    )


def conta_excluida(email, resumo):
    return _enviar(
        "Sua conta foi excluída",
        "emails/conta-excluida.txt",
        {"resumo": resumo},
        [email],
    )
