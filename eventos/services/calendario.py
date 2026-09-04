"""Exportação .ics (RFC 5545) e link para o Google Agenda.

Sem biblioteca: um VEVENT é texto simples e o formato é estável há vinte anos.
Adicionar uma dependência para escrever oito linhas não se justifica.
"""

from datetime import UTC
from urllib.parse import urlencode

from django.utils import timezone

QUEBRA = "\r\n"  # A RFC exige CRLF.
LIMITE_LINHA = 73  # 75 octetos menos a margem do "folding".


def _escapar(texto):
    if not texto:
        return ""
    return (
        str(texto)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _dobrar(linha):
    """Linhas com mais de 75 octetos precisam continuar com um espaço na frente."""
    if len(linha) <= LIMITE_LINHA:
        return linha
    pedacos = [linha[:LIMITE_LINHA]]
    resto = linha[LIMITE_LINHA:]
    while resto:
        pedacos.append(" " + resto[: LIMITE_LINHA - 1])
        resto = resto[LIMITE_LINHA - 1 :]
    return QUEBRA.join(pedacos)


def _utc(momento):
    # `django.utils.timezone.utc` foi removido no Django 5.0. O fuso UTC agora
    # vem da biblioteca padrão; `timezone` aqui é sempre o do Django.
    return timezone.localtime(momento, UTC).strftime("%Y%m%dT%H%M%SZ")


def vevent(evento, url_absoluta, dominio="finde"):
    local = evento.local
    if evento.endereco:
        local = f"{local}, {evento.endereco}"
    if evento.cidade:
        local = f"{local} — {evento.cidade}"

    descricao = evento.resumo or (evento.descricao or "")[:500]
    if url_absoluta:
        descricao = f"{descricao}\n\n{url_absoluta}".strip()

    linhas = [
        "BEGIN:VEVENT",
        f"UID:evento-{evento.pk}@{dominio}",
        f"DTSTAMP:{_utc(timezone.now())}",
        f"DTSTART:{_utc(evento.data)}",
        f"DTEND:{_utc(evento.termino)}",
        f"SUMMARY:{_escapar(evento.nome)}",
        f"LOCATION:{_escapar(local)}",
        f"DESCRIPTION:{_escapar(descricao)}",
        f"URL:{url_absoluta}",
        "STATUS:CONFIRMED",
    ]
    if evento.tem_coordenadas:
        linhas.append(f"GEO:{evento.latitude};{evento.longitude}")
    if evento.organizador_nome:
        linhas.append(f"ORGANIZER;CN={_escapar(evento.organizador_nome)}:mailto:noreply@{dominio}")
    linhas.append("END:VEVENT")
    return linhas


def calendario(eventos, url_de, nome="Finde", dominio="finde"):
    """Monta um .ics com um ou muitos eventos."""
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{nome}//Agenda de Brasilia//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapar(nome)}",
        "X-WR-TIMEZONE:America/Sao_Paulo",
    ]
    for evento in eventos:
        linhas.extend(vevent(evento, url_de(evento), dominio))
    linhas.append("END:VCALENDAR")
    return QUEBRA.join(_dobrar(linha) for linha in linhas) + QUEBRA


def nome_de_arquivo(evento):
    from django.utils.text import slugify

    return f"{slugify(evento.nome)[:60] or 'evento'}.ics"


def link_google_agenda(evento, url_absoluta):
    local = ", ".join(p for p in [evento.local, evento.endereco, evento.cidade] if p)
    detalhes = evento.resumo or (evento.descricao or "")[:400]
    if url_absoluta:
        detalhes = f"{detalhes}\n{url_absoluta}".strip()
    parametros = {
        "action": "TEMPLATE",
        "text": evento.nome,
        "dates": f"{_utc(evento.data)}/{_utc(evento.termino)}",
        "details": detalhes,
        "location": local,
        "ctz": "America/Sao_Paulo",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(parametros)
