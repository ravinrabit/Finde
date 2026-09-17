from django.db import transaction
from django.utils import timezone

VERSAO_TERMOS = "2026-09-16"
VERSAO_PRIVACIDADE = "2026-09-16"


def _iso(momento):
    return timezone.localtime(momento).isoformat() if momento else None


def exportar_dados(user):
    from ..models import AceiteDeTermos, Evento, Favorito, Ingresso, Produtor

    dados = {
        "gerado_em": _iso(timezone.now()),
        "conta": {
            "id": user.pk,
            "nome": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email,
            "usuario": user.username,
            "criada_em": _iso(user.date_joined),
            "ultimo_acesso": _iso(user.last_login),
        },
        "aceites": [
            {
                "termos": a.versao_termos,
                "privacidade": a.versao_privacidade,
                "em": _iso(a.aceito_em),
                "ip": a.ip,
            }
            for a in AceiteDeTermos.objects.filter(usuario=user)
        ],
        "ingressos": [
            {
                "codigo": str(i.codigo),
                "evento": i.evento.nome,
                "evento_url": i.evento.get_absolute_url(),
                "data_do_evento": _iso(i.evento.data),
                "tipo": i.get_tipo_display(),
                "status": i.get_status_display(),
                "valor": str(i.valor),
                "reservado_em": _iso(i.data_compra),
            }
            for i in Ingresso.objects.filter(usuario=user).select_related("evento")
        ],
        "favoritos": [
            {
                "evento": f.evento.nome,
                "evento_url": f.evento.get_absolute_url(),
                "salvo_em": _iso(f.criado_em),
            }
            for f in Favorito.objects.filter(usuario=user).select_related("evento")
        ],
        "eventos_publicados": [
            {
                "nome": e.nome,
                "url": e.get_absolute_url(),
                "status": e.get_status_display(),
                "criado_em": _iso(e.criado_em),
            }
            for e in Evento.objects.filter(criado_por=user)
        ],
    }

    produtor = Produtor.objects.filter(user=user).first()
    if produtor:
        dados["perfil_produtor"] = {
            "nome": produtor.nome,
            "bio": produtor.bio,
            "email": produtor.email,
            "site": produtor.site,
            "instagram": produtor.instagram,
            "whatsapp": produtor.whatsapp,
            "verificado": produtor.verificado,
            "url": produtor.get_absolute_url(),
        }

    return dados


@transaction.atomic
def excluir_conta(user):
    from ..models import Evento, Produtor

    resumo = {
        "eventos_preservados": Evento.objects.filter(criado_por=user).count(),
        "ingressos_removidos": user.ingressos.count(),
        "favoritos_removidos": user.favoritos.count(),
    }

    Produtor.objects.filter(user=user).update(user=None)
    Evento.objects.filter(criado_por=user).update(criado_por=None)
    user.delete()
    return resumo
