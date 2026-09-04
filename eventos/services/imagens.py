"""Capas em vários tamanhos, em WebP.

O problema resolvido: um JPEG de 5 MB (o limite aceito no upload) era baixado
inteiro para preencher um card de 400x250. Doze cards podiam significar 60 MB.

Estratégia: no upload, gerar 400/800/1200 px de largura em WebP ao lado do
original e montar o srcset. Usa só Pillow, que já é dependência.
"""

import logging
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger("eventos")

SUFIXO = "__{largura}w.webp"


def caminho_variante(caminho_original, largura):
    raiz, _ = os.path.splitext(caminho_original)
    return raiz + SUFIXO.format(largura=largura)


def gerar_variantes(arquivo_campo, larguras=None, forcar=False):
    """Cria as versões redimensionadas. Devolve {largura: caminho}.

    Falha de geração não derruba o salvamento: sem variante, o template cai no
    original.
    """
    if not arquivo_campo:
        return {}
    larguras = larguras or getattr(settings, "IMAGEM_LARGURAS", (400, 800, 1200))
    qualidade = getattr(settings, "IMAGEM_QUALIDADE_WEBP", 82)

    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        logger.warning("Pillow indisponível: capas serão servidas no tamanho original.")
        return {}

    resultado = {}
    try:
        arquivo_campo.open("rb")
        original = Image.open(arquivo_campo)
        original = ImageOps.exif_transpose(original)
        if original.mode not in ("RGB", "RGBA"):
            original = original.convert("RGB")
        largura_real = original.width
    except Exception as erro:
        logger.warning("Não foi possível abrir a capa %s: %s", arquivo_campo.name, erro)
        return {}

    for largura in sorted(larguras):
        destino = caminho_variante(arquivo_campo.name, largura)
        if not forcar and default_storage.exists(destino):
            resultado[largura] = destino
            continue
        if largura_real and largura > largura_real * 1.2:
            continue  # não faz sentido ampliar
        try:
            copia = original.copy()
            copia.thumbnail((largura, largura * 3), Image.LANCZOS)
            buffer = BytesIO()
            copia.save(buffer, format="WEBP", quality=qualidade, method=4)
            default_storage.save(destino, ContentFile(buffer.getvalue()))
            resultado[largura] = destino
        except Exception as erro:
            logger.warning("Falha ao gerar variante %dw de %s: %s", largura, arquivo_campo.name, erro)

    return resultado


def srcset(arquivo_campo, larguras=None):
    """String pronta para o atributo srcset, só com as variantes que existem."""
    if not arquivo_campo:
        return ""
    larguras = larguras or getattr(settings, "IMAGEM_LARGURAS", (400, 800, 1200))
    partes = []
    for largura in sorted(larguras):
        caminho = caminho_variante(arquivo_campo.name, largura)
        try:
            if default_storage.exists(caminho):
                partes.append(f"{default_storage.url(caminho)} {largura}w")
        except Exception:  # storages remotos podem falhar no exists()
            continue
    return ", ".join(partes)


def remover_variantes(caminho_original, larguras=None):
    larguras = larguras or getattr(settings, "IMAGEM_LARGURAS", (400, 800, 1200))
    for largura in larguras:
        caminho = caminho_variante(caminho_original, largura)
        try:
            if default_storage.exists(caminho):
                default_storage.delete(caminho)
        except Exception:
            continue
