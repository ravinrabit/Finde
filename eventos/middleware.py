"""Middlewares próprios do Finde."""

import logging

from django.conf import settings
from django.http import Http404

from .ratelimit import excedeu, ip_do_pedido, resposta_429

logger = logging.getLogger("eventos.seguranca")


class RestringirAdminMiddleware:
    """Endurece o painel administrativo.

    1. O caminho do admin é configurável (ADMIN_URL). Não impede um ataque
       determinado, mas tira o /admin/ das varreduras automatizadas.
    2. ADMIN_IPS_PERMITIDOS restringe o acesso por origem. Vazio = liberado.
    3. Tentativas de POST no admin entram no mesmo contador de 'login'.
    4. Todo acesso negado vai para o log de segurança.

    Responde 404, não 403: negar a existência dá menos informação do que negar
    a permissão.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefixo = f"/{settings.ADMIN_URL.strip('/')}/" if settings.ADMIN_URL else "/admin/"
        self.permitidos = {ip.strip() for ip in settings.ADMIN_IPS_PERMITIDOS if ip.strip()}

    def __call__(self, request):
        if request.path.startswith(self.prefixo):
            origem = ip_do_pedido(request)

            if self.permitidos and origem not in self.permitidos:
                logger.warning("Acesso ao admin negado para %s (%s)", origem, request.path)
                raise Http404

            if request.method == "POST" and excedeu("login", request):
                logger.warning("Limite de tentativas no admin excedido por %s", origem)
                return resposta_429(request)

        return self.get_response(request)
