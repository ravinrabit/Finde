import os

_AMBIENTE = os.environ.get("DJANGO_ENV", "").strip().lower()

if not _AMBIENTE:
    try:
        from decouple import config

        _AMBIENTE = config("DJANGO_ENV", default="dev").strip().lower()
    except Exception:
        _AMBIENTE = "dev"

if _AMBIENTE in {"prod", "producao", "produção", "production"}:
    from .prod import *
elif _AMBIENTE in {"test", "teste", "testes"}:
    from .test import *
else:
    from .dev import *
