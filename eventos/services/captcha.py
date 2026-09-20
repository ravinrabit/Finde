import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("eventos.seguranca")

VERIFICACAO_URL = "https://hcaptcha.com/siteverify"
TIMEOUT_SEGUNDOS = 10


def verificar(token, ip=None):
    """Confere a resposta do hCaptcha com o serviço deles.

    Devolve False (nunca levanta) sempre que a verificação falha por
    qualquer motivo — token ausente, rede fora do ar, resposta malformada —
    porque o chamador trata isso como "recusa o formulário", não como erro.
    """
    if not getattr(settings, "HCAPTCHA_ATIVO", True):
        return True
    if not token:
        return False

    dados = {"secret": settings.HCAPTCHA_SECRET_KEY, "response": token}
    if ip:
        dados["remoteip"] = ip

    corpo = urllib.parse.urlencode(dados).encode("utf-8")
    pedido = urllib.request.Request(VERIFICACAO_URL, data=corpo, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resposta:
            resultado = json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:
        logger.warning("Falha ao verificar hCaptcha: %s", erro)
        return False

    return bool(resultado.get("success"))
