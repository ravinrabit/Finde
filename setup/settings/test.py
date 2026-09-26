from .base import *

DEBUG = False
SECRET_KEY = "chave-so-para-testes-nao-usar-em-producao"
ALLOWED_HOSTS = ["*"]

MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {"transaction_mode": "IMMEDIATE"},
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "testes"},
    "paginas": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "testes-paginas"},
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

RATELIMIT_ATIVO = False
CACHE_PAGINA_ATIVO = False

GEOCODING_ATIVO = False
IA_ATIVO = False
HCAPTCHA_ATIVO = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"nulo": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["nulo"], "level": "CRITICAL"},
}
