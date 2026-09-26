import urllib.parse


def config_de_database_url(url):
    
    partes = urllib.parse.urlsplit(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": urllib.parse.unquote(partes.path.lstrip("/")),
        "USER": urllib.parse.unquote(partes.username) if partes.username else partes.username,
        "PASSWORD": urllib.parse.unquote(partes.password) if partes.password else partes.password,
        "HOST": partes.hostname,
        "PORT": partes.port or 5432,
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
    }
