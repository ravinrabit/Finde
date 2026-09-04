from django.conf import settings


def identidade(request):
    """Nome e descrição do produto vêm da configuração, não do HTML.

    Os antigos ATALHOS_PERIODO e CATEGORIAS_MENU saíram: nenhum template os
    usava, e um context processor roda em toda requisição do site.
    """
    return {
        "SITE_NOME": settings.SITE_NOME,
        "SITE_DESCRICAO": settings.SITE_DESCRICAO,
        "SITE_DOMINIO": settings.SITE_DOMINIO,
        "EMAIL_CONTATO": settings.EMAIL_CONTATO,
    }
