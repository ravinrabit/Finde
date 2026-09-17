import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from . import busca as servico_busca
from ..models import Evento

logger = logging.getLogger("eventos")

MAXIMO_EVENTOS_NO_CONTEXTO = 8

SOBRE_O_SITE = (
    "Você é o assistente do Finde, um site que reúne a agenda de eventos de "
    "Brasília e do Distrito Federal. Responda em português, de forma curta e "
    "direta. Use só os eventos listados abaixo em 'EVENTOS ENCONTRADOS' para "
    "recomendar programação — nunca invente nome, data, local ou preço de "
    "evento. Se não houver nenhum evento relevante na lista, diga isso e "
    "sugira a pessoa buscar em /eventos/ ou ajustar os filtros.\n\n"
    "Sobre o site, quando perguntarem:\n"
    "- Cadastro é gratuito; reserva de ingresso também, quando o evento é "
    "gratuito; eventos pagos mostram o preço na página.\n"
    "- Qualquer pessoa pode publicar um evento em /criar-evento/; ele passa "
    "por uma revisão rápida da equipe antes de aparecer no site.\n"
    "- Meus dados (exportar ou excluir a conta) fica em /conta/privacidade/.\n"
    "- Dúvidas que você não souber responder, oriente a pessoa a usar a "
    "página /contato/."
)


class AssistenteIndisponivel(Exception):
    pass


def contexto_de_eventos(pergunta):
    eventos = servico_busca.aplicar(Evento.objects.visiveis().para_cards(), pergunta)
    eventos = eventos.order_by("data")[:MAXIMO_EVENTOS_NO_CONTEXTO]
    linhas = []
    for evento in eventos:
        linhas.append(
            f"- {evento.nome} | {timezone.localtime(evento.data):%d/%m/%Y %H:%M} | "
            f"{evento.local} | {evento.preco_rotulo} | {evento.get_absolute_url()}"
        )
    return "\n".join(linhas) if linhas else "(nenhum evento encontrado para essa busca)"


def responder(pergunta, historico=None):
    if not getattr(settings, "IA_ATIVO", True):
        raise AssistenteIndisponivel("Assistente desligado nesta configuração.")

    mensagens = [
        {
            "role": "system",
            "content": f"{SOBRE_O_SITE}\n\nEVENTOS ENCONTRADOS:\n{contexto_de_eventos(pergunta)}",
        },
        *(historico or []),
        {"role": "user", "content": pergunta},
    ]

    corpo = json.dumps({
        "model": settings.IA_MODELO,
        "messages": mensagens,
        "stream": False,
    }).encode("utf-8")

    cabecalhos = {"Content-Type": "application/json"}
    if settings.IA_API_KEY:
        cabecalhos["Authorization"] = f"Bearer {settings.IA_API_KEY}"

    pedido = urllib.request.Request(
        f"{settings.IA_API_BASE.rstrip('/')}/chat/completions",
        data=corpo,
        headers=cabecalhos,
        method="POST",
    )

    try:
        with urllib.request.urlopen(pedido, timeout=settings.IA_TIMEOUT) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as erro:
        logger.warning("Assistente indisponível: %s", erro)
        raise AssistenteIndisponivel(str(erro)) from erro
    except json.JSONDecodeError as erro:
        raise AssistenteIndisponivel("Resposta inválida do provedor de IA.") from erro

    try:
        return dados["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as erro:
        raise AssistenteIndisponivel("Resposta inesperada do provedor de IA.") from erro
