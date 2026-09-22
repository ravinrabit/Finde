import urllib.parse


def config_de_database_url(url):
    """Provedores como o Render costumam oferecer uma URL única pronta (às
    vezes até "linkada" direto no painel, sem o valor passar pela nossa mão)
    em vez de host/usuário/senha separados.

    username/password/path vêm com escape de URL (%40 pra "@" etc) e
    urlsplit NÃO desfaz isso sozinho — sem o unquote, uma senha gerada com
    caractere especial (bem comum) chega errada pro driver do Postgres.
    """
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
