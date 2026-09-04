"""Desenvolvimento local."""

from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = config("DEBUG", default=True, cast=bool)

# Sem manifesto: em dev o collectstatic não precisa ter rodado.
STORAGES = {
    **STORAGES,  # noqa: F405
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

INTERNAL_IPS = ["127.0.0.1"]
