"""Execução da suíte de testes. Rápido, isolado e sem efeitos externos."""

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "chave-so-para-testes-nao-usar-em-producao"
ALLOWED_HOSTS = ["*"]

# O WhiteNoise serve arquivo estático — não tem papel nenhum em teste, e
# manter o middleware fazia a suíte inteira depender de um pacote que só
# importa em produção. Um ambiente sem ele derrubava 140 testes com
# ModuleNotFoundError, escondendo as falhas de verdade.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "testes"}}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Cada teste que precisa de limite liga o seu explicitamente.
RATELIMIT_ATIVO = False

# Nenhuma chamada de rede durante os testes.
GEOCODING_ATIVO = False
SYMPLA_SCRAPING_ATIVO = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"nulo": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["nulo"], "level": "CRITICAL"},
}
