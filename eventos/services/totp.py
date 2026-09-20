"""TOTP (RFC 6238) sem depender de pacote de terceiros — só o que o Google
Authenticator, Authy etc. já esperam: HMAC-SHA1, 6 dígitos, passo de 30s.
"""

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
import urllib.parse

import qrcode

PASSO_SEGUNDOS = 30
DIGITOS = 6
JANELA_PADRAO = 1  # tolera 1 passo (30s) de diferença de relógio pra cada lado


def gerar_segredo():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def uri_provisionamento(segredo, identificador, emissor="Finde"):
    rotulo = urllib.parse.quote(f"{emissor}:{identificador}")
    parametros = urllib.parse.urlencode({
        "secret": segredo,
        "issuer": emissor,
        "algorithm": "SHA1",
        "digits": DIGITOS,
        "period": PASSO_SEGUNDOS,
    })
    return f"otpauth://totp/{rotulo}?{parametros}"


def _codigo_para_contador(segredo, contador):
    enchimento = "=" * ((8 - len(segredo) % 8) % 8)
    chave = base64.b32decode(segredo.upper() + enchimento)
    bloco = struct.pack(">Q", contador)
    resumo = hmac.new(chave, bloco, hashlib.sha1).digest()
    deslocamento = resumo[-1] & 0x0F
    fragmento = struct.unpack(">I", resumo[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF
    return f"{fragmento % (10 ** DIGITOS):0{DIGITOS}d}"


def codigo_atual(segredo, quando=None):
    contador = int((quando if quando is not None else time.time()) // PASSO_SEGUNDOS)
    return _codigo_para_contador(segredo, contador)


def qr_code_base64(uri):
    imagem = qrcode.make(uri)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def verificar(segredo, codigo, janela=JANELA_PADRAO):
    codigo = (codigo or "").strip()
    if not codigo.isdigit() or len(codigo) != DIGITOS:
        return False
    contador_atual = int(time.time() // PASSO_SEGUNDOS)
    return any(
        hmac.compare_digest(_codigo_para_contador(segredo, contador_atual + deslocamento), codigo)
        for deslocamento in range(-janela, janela + 1)
    )
