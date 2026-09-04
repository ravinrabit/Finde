"""Seleciona o módulo de configuração conforme DJANGO_ENV.

Mantém DJANGO_SETTINGS_MODULE=setup.settings funcionando como antes, para não
quebrar manage.py, wsgi.py, asgi.py nem nenhum script de deploy existente.

    DJANGO_ENV=dev   (padrão)
    DJANGO_ENV=test
    DJANGO_ENV=prod
"""

import os

_AMBIENTE = os.environ.get("DJANGO_ENV", "").strip().lower()

if not _AMBIENTE:
    try:
        from decouple import config

        _AMBIENTE = config("DJANGO_ENV", default="dev").strip().lower()
    except Exception:  # pragma: no cover - decouple sempre está instalado
        _AMBIENTE = "dev"

if _AMBIENTE in {"prod", "producao", "produção", "production"}:
    from .prod import *  # noqa: F401,F403
elif _AMBIENTE in {"test", "teste", "testes"}:
    from .test import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
