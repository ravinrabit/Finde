"""Produção. Falha cedo se algo essencial estiver faltando."""

from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = False

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

if SENTRY_DSN:  # noqa: F405
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,  # noqa: F405
            integrations=[DjangoIntegration()],
            traces_sample_rate=config("SENTRY_TRACES", default=0.05, cast=float),
            send_default_pii=False,
            environment="production",
        )
    except ImportError:  # pragma: no cover
        import logging

        logging.getLogger("eventos").warning(
            "SENTRY_DSN configurado mas o pacote sentry-sdk não está instalado."
        )
