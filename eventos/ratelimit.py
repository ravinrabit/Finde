"""Limite de tentativas sem dependência externa.

Por que não django-ratelimit ou django-axes: o projeto inteiro tem quatro
dependências e roda em qualquer lugar. Um contador de janela fixa sobre o cache
do Django resolve o problema real (força bruta em login, criação em massa de
contas, reserva ilimitada de ingressos) em 80 linhas e sem pacote novo.

Limitações honestas:
- Janela fixa, não deslizante: em teoria dá para gastar 2x o limite na virada
  da janela. Aceitável para o que se está protegendo aqui.
- Depende do cache. Com CACHE_BACKEND=locmem e vários workers, cada worker tem
  o próprio contador. Em produção use `db` ou `redis` (ver .env.example).

Se um dia o projeto precisar de bloqueio persistente de conta, aí sim vale
trocar por django-axes.
"""

import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger("eventos.seguranca")

CABECALHOS_DE_PROXY = ("HTTP_X_FORWARDED_FOR", "HTTP_X_REAL_IP")


def ip_do_pedido(request):
    """IP do cliente. Confia em X-Forwarded-For apenas quando há proxy declarado.

    SECURE_PROXY_SSL_HEADER só é definido em produção, atrás de proxy reverso.
    Fora disso, o cabeçalho é forjável e é ignorado — senão o limite viraria
    decoração.
    """
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        for cabecalho in CABECALHOS_DE_PROXY:
            valor = request.META.get(cabecalho, "")
            if valor:
                return valor.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _chave(nome, request, por_usuario):
    if por_usuario and request.user.is_authenticated:
        return f"rl:{nome}:u{request.user.pk}"
    return f"rl:{nome}:{ip_do_pedido(request)}"


def excedeu(nome, request, por_usuario=False):
    """Conta a tentativa e diz se o limite foi ultrapassado."""
    if not getattr(settings, "RATELIMIT_ATIVO", True):
        return False
    limite, janela = settings.RATELIMITS.get(nome, (60, 60))
    chave = _chave(nome, request, por_usuario)

    # add() só grava se a chave não existir: é o que dá o TTL da janela.
    if cache.add(chave, 1, janela):
        return False
    try:
        atual = cache.incr(chave)
    except ValueError:
        # A chave expirou entre o add e o incr.
        cache.set(chave, 1, janela)
        return False
    return atual > limite


def limpar(nome, request, por_usuario=False):
    """Zera o contador. Chamado quando a ação dá certo (ex.: login válido)."""
    cache.delete(_chave(nome, request, por_usuario))


def limitar(nome, metodos=("POST",), por_usuario=False, mensagem=None):
    """Decorador de view.

    Responde 429 com a página de erro do site, ou JSON quando o pedido é XHR.
    """

    def decorador(view):
        @wraps(view)
        def envelope(request, *args, **kwargs):
            if request.method in metodos and excedeu(nome, request, por_usuario):
                logger.warning(
                    "Limite '%s' excedido por %s em %s", nome, ip_do_pedido(request), request.path
                )
                return resposta_429(request, mensagem)
            return view(request, *args, **kwargs)

        return envelope

    return decorador


def resposta_429(request, mensagem=None):
    texto = mensagem or "Muitas tentativas em pouco tempo. Espere alguns minutos e tente de novo."
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"erro": texto}, status=429)
    resposta = render(request, "429.html", {"mensagem": texto}, status=429)
    resposta["Retry-After"] = "900"
    return resposta
