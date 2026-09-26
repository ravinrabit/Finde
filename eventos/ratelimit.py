import logging
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger("eventos.seguranca")

def ip_do_pedido(request):

    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        bruto = request.META.get("HTTP_X_FORWARDED_FOR", "")
        partes = [parte.strip() for parte in bruto.split(",") if parte.strip()]
        if partes:
            return partes[-1]
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _chave(nome, request, por_usuario):
    if por_usuario and request.user.is_authenticated:
        return f"rl:{nome}:u{request.user.pk}"
    return f"rl:{nome}:{ip_do_pedido(request)}"


def excedeu(nome, request, por_usuario=False):
    if not getattr(settings, "RATELIMIT_ATIVO", True):
        return False
    limite, janela = settings.RATELIMITS.get(nome, (60, 60))
    chave = _chave(nome, request, por_usuario)


    if cache.add(chave, 1, janela):
        return False
    try:
        atual = cache.incr(chave)
    except ValueError:

        cache.set(chave, 1, janela)
        return False
    return atual > limite


def limpar(nome, request, por_usuario=False):
    cache.delete(_chave(nome, request, por_usuario))


def limitar(nome, metodos=("POST",), por_usuario=False, mensagem=None):
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
