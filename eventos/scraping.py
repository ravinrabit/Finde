"""Compatibilidade: o pacote foi renomeado para eventos.ingestao.

Mantido para não quebrar código externo, script de deploy ou import antigo.
Será removido depois que o desligamento do Selenium estiver concluído.
"""

import warnings

from .ingestao import EventoImportado, salvar_importados  # noqa: F401

warnings.warn(
    "eventos.scraping virou eventos.ingestao. Atualize o import.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["EventoImportado", "salvar_importados"]
