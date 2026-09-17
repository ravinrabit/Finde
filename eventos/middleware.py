import logging

from django.conf import settings
from django.http import Http404

from .ratelimit import excedeu, ip_do_pedido, resposta_429

logger = logging.getLogger("eventos.seguranca")


class RestringirAdminMiddleware:
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
