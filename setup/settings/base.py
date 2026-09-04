"""Configuração compartilhada por todos os ambientes.

Os módulos dev.py, test.py e prod.py importam daqui e ajustam o que muda.
O ambiente é escolhido pela variável DJANGO_ENV (ver setup/settings/__init__.py).
"""

from pathlib import Path

from decouple import Csv, config
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,10.0.2.2", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

SITE_NOME = config("SITE_NOME", default="Finde")
SITE_DESCRICAO = "O que acontece em Brasília, num só lugar."
SITE_DOMINIO = config("SITE_DOMINIO", default="localhost")

ADMIN_URL = config("ADMIN_URL", default="admin").strip("/")
ADMIN_IPS_PERMITIDOS = config("ADMIN_IPS_PERMITIDOS", default="", cast=Csv())


# =========================
# APLICAÇÕES
# =========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "eventos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "eventos.middleware.RestringirAdminMiddleware",
]

ROOT_URLCONF = "setup.urls"
WSGI_APPLICATION = "setup.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "setup" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "eventos.context_processors.identidade",
            ],
            # Registrar a biblioteca como builtin evita ter que repetir
            # {% load finde %} em cada template — e evita que um {% load %}
            # esquecido derrube uma página só na hora de renderizar.
            "builtins": ["eventos.templatetags.finde"],
        },
    },
]


# =========================
# BANCO DE DADOS
# =========================

if config("DB_ENGINE", default="sqlite") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "CONN_MAX_AGE": 600,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL;"},
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =========================
# CACHE
# =========================

_CACHE_BACKEND = config("CACHE_BACKEND", default="locmem")

if _CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": config("REDIS_URL", default="redis://127.0.0.1:6379/1"),
        }
    }
elif _CACHE_BACKEND == "db":
    # Requer: python manage.py createcachetable
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "finde_cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "finde",
        }
    }


# =========================
# AUTENTICAÇÃO
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# =========================
# RATE LIMITING
# =========================
# (limite de tentativas, janela em segundos). Ver eventos/ratelimit.py.

RATELIMIT_ATIVO = config("RATELIMIT_ATIVO", default=True, cast=bool)
RATELIMITS = {
    "login": (10, 15 * 60),
    "cadastro": (5, 60 * 60),
    "senha_reset": (5, 60 * 60),
    "reserva": (20, 60 * 60),
    "busca": (120, 60),
    "favorito": (60, 60),
    "colar_link": (20, 60 * 60),
    "excluir_conta": (5, 60 * 60),
}


# =========================
# E-MAIL
# =========================

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default=f"{SITE_NOME} <nao-responda@{SITE_DOMINIO}>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_CONTATO = config("EMAIL_CONTATO", default=f"contato@{SITE_DOMINIO}")
EMAIL_ENCARREGADO_LGPD = config("EMAIL_ENCARREGADO_LGPD", default=EMAIL_CONTATO)

if config("EMAIL_HOST", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = config("EMAIL_HOST")
    EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
    EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# =========================
# INTERNACIONALIZAÇÃO
# =========================

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# =========================
# ARQUIVOS ESTÁTICOS E MÍDIA
# =========================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

_MEDIA_BACKEND = config("MEDIA_BACKEND", default="local")

if _MEDIA_BACKEND == "s3":
    # Requer: pip install django-storages[s3]
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_ENDPOINT_URL = config("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default=None)
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="auto")
    AWS_QUERYSTRING_AUTH = False
    AWS_DEFAULT_ACL = None
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=31536000, immutable"}
    _STORAGE_PADRAO = "storages.backends.s3.S3Storage"
else:
    _STORAGE_PADRAO = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {"BACKEND": _STORAGE_PADRAO},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Tamanhos gerados para cada capa enviada (largura em px).
IMAGEM_LARGURAS = (400, 800, 1200)
IMAGEM_QUALIDADE_WEBP = 82

DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200


# =========================
# INGESTÃO
# =========================

MAPA_NAS_NUVENS_URL = config("MAPA_NAS_NUVENS_URL", default="http://mapa.cultura.df.gov.br")
GEOCODING_URL = config("GEOCODING_URL", default="https://nominatim.openstreetmap.org/search")
GEOCODING_USER_AGENT = config("GEOCODING_USER_AGENT", default=f"Finde/1.0 (+https://{SITE_DOMINIO})")
GEOCODING_PAUSA_SEGUNDOS = config("GEOCODING_PAUSA_SEGUNDOS", default=1.1, cast=float)
GEOCODING_LIMITE_POR_EXECUCAO = config("GEOCODING_LIMITE_POR_EXECUCAO", default=100, cast=int)
GEOCODING_CACHE_SEGUNDOS = 60 * 60 * 24 * 30
SYMPLA_SCRAPING_ATIVO = config("SYMPLA_SCRAPING_ATIVO", default=False, cast=bool)
INGESTAO_HTTP_TIMEOUT = 20


# =========================
# SEGURANÇA
# =========================

SECURE_CSP = {
    "default-src": [CSP.SELF],
    # O site não emite script nem style inline. O nonce existe para o /admin/,
    # que usa blocos inline assinados.
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    "font-src": [CSP.SELF],
    # Capas de eventos importados ainda podem vir de CDNs externas enquanto a
    # cópia local não roda. Ver "manage.py baixar_capas".
    "img-src": [CSP.SELF, "data:", "blob:", "https:"],
    "connect-src": [CSP.SELF],
    "form-action": [CSP.SELF],
    "base-uri": [CSP.SELF],
    "object-src": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
}

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"


# =========================
# OBSERVABILIDADE
# =========================

LOG_LEVEL = config("LOG_LEVEL", default="INFO")
SENTRY_DSN = config("SENTRY_DSN", default="")
HEALTHCHECK_TOKEN = config("HEALTHCHECK_TOKEN", default="")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simples": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
        "detalhado": {
            "format": "{levelname} {asctime} {name} {module}:{lineno} {process:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simples"},
        "console_detalhado": {"class": "logging.StreamHandler", "formatter": "detalhado"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console_detalhado"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console_detalhado"], "level": "WARNING", "propagate": False},
        "eventos": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "eventos.seguranca": {"handlers": ["console_detalhado"], "level": "INFO", "propagate": False},
        "eventos.ingestao": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
