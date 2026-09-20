from django.conf import settings


def identidade(request):
    return {
        "SITE_NOME": settings.SITE_NOME,
        "SITE_DESCRICAO": settings.SITE_DESCRICAO,
        "SITE_DOMINIO": settings.SITE_DOMINIO,
        "EMAIL_CONTATO": settings.EMAIL_CONTATO,
        "HCAPTCHA_SITE_KEY": settings.HCAPTCHA_SITE_KEY,
    }
