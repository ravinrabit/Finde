from decouple import config

from .base import *

DEBUG = config("DEBUG", default=True, cast=bool)

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

INTERNAL_IPS = ["127.0.0.1"]
