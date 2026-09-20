"""Criptografia simétrica pra dado sensível que precisa ser lido de volta
(diferente de senha, que só é comparada por hash). Chave derivada da
SECRET_KEY do Django — trocar a SECRET_KEY também invalida tudo cifrado
com ela, então rotacionar as duas juntas quando for o caso.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class FalhaAoDecifrar(Exception):
    pass


def _chave():
    resumo = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(resumo)


def cifrar(texto):
    return Fernet(_chave()).encrypt(texto.encode("utf-8"))


def decifrar(dados_cifrados):
    try:
        return Fernet(_chave()).decrypt(bytes(dados_cifrados)).decode("utf-8")
    except InvalidToken as erro:
        raise FalhaAoDecifrar("Não foi possível decifrar — SECRET_KEY mudou?") from erro
