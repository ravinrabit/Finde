"""Direitos do titular, de verdade.

A política de privacidade promete acesso, correção, portabilidade e exclusão.
Antes disso existir, a promessa apontava para uma central de ajuda que não tinha
canal de contato nenhum.

Duas operações são cobertas aqui:
  exportar_dados(user) -> dicionário serializável em JSON (portabilidade)
  excluir_conta(user)  -> anonimiza o que precisa ficar e apaga o resto
"""

from django.db import transaction
from django.utils import timezone

VERSAO_TERMOS = "2026-09"
VERSAO_PRIVACIDADE = "2026-09"


def _iso(momento):
    return timezone.localtime(momento).isoformat() if momento else None


def exportar_dados(user):
    """Tudo que o Finde guarda sobre a pessoa, em estrutura plana.

    Não inclui credenciais (o hash da senha não é dado do titular, é controle
    de acesso) nem tokens de integração de terceiros.
    """
    from ..models import AceiteDeTermos, Evento, Favorito, Ingresso

    return {
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


@transaction.atomic
def excluir_conta(user):
    """Apaga a conta preservando o que não é dado pessoal.

    Decisões, e o porquê de cada uma:
      - Ingressos e favoritos somem (CASCADE). São dados só da pessoa.
      - Eventos publicados FICAM, sem autor (criado_por já é SET_NULL). Apagar
        derrubaria a agenda pública e prejudicaria terceiros que reservaram.
      - Se a pessoa era produtor, o Produtor fica, desvinculado do usuário: a
        página pública continua, os eventos continuam.
      - O usuário é apagado de fato, não desativado. "Direito à exclusão" com
        a linha continuando no banco não é exclusão.
    """
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
