import logging

from django.apps import AppConfig

logger = logging.getLogger("eventos")


class EventosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "eventos"
    verbose_name = "Eventos"

    def ready(self):
        from . import signals  # noqa: F401

        # Sem isso, uma mudança de template/CSS só aparece pra visitante
        # anônimo depois que o cache de páginas expirar sozinho (até 180s) -
        # e com CACHE_BACKEND=redis/db isso nem depende do processo reiniciar,
        # fica preso até vencer. Limpa a cada subida do processo (todo
        # deploy), então o primeiro request depois de um deploy já é fresco.
        try:
            from django.core.cache import caches

            caches["paginas"].clear()
        except Exception as erro:  # pragma: no cover
            # Cache (Redis/tabela do banco) pode não estar pronto ainda na
            # primeira subida - não é motivo pra derrubar o processo inteiro.
            logger.warning("Não foi possível limpar o cache de páginas no startup: %s", erro)
