"""Camada de ingestão de eventos.

Antes se chamava "scraping", o que descrevia uma das fontes, não a arquitetura.
Toda fonte — API pública, feed .ics, JSON-LD de parceiro, link colado por um
produtor — produz `EventoImportado` e passa por `salvar_importados()`. É esse
contrato que torna trocar de fonte um detalhe.

O módulo antigo `eventos.scraping` continua importável por um ciclo de
depreciação (ver eventos/scraping.py).
"""

from .base import EventoImportado, salvar_importados  # noqa: F401 (reexportação)

__all__ = ["EventoImportado", "salvar_importados"]
