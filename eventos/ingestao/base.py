"""Contrato único de ingestão.

Todo conector, independente da fonte, produz `EventoImportado` e entrega a
`salvar_importados()`. Quem grava no banco é só esta função — assim a política
de curadoria, a idempotência e o vínculo com Local/Produtor ficam num lugar só.

O que mudou em relação à versão anterior:
  - evento importado entra como PENDENTE, nunca publicado direto;
  - data sem fuso deixou de virar UTC silenciosamente (era erro de 3 horas);
  - o local vira um registro de Local, e o organizador vira um Produtor.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from ..constants import Categoria, Regiao, normalizar
from ..models import Evento, Local, Produtor

logger = logging.getLogger("eventos.ingestao")

_ROTULOS_REGIAO = sorted(
    ((slugify(r.label), r.value) for r in Regiao if r != Regiao.ONLINE),
    key=lambda par: len(par[0]),
    reverse=True,
)
_VALORES_CATEGORIA = {c.value for c in Categoria}

# Rótulos curtos casam dentro de outras palavras ("gama" em "gamarra"). Para
# esses, só vale a palavra inteira.
_ROTULOS_CURTOS = {"gama", "guara", "cruzeiro", "paranoa", "noroeste", "sudoeste"}


def garantir_aware(momento):
    """Data sem fuso é interpretada no fuso do projeto, não em UTC.

    Com USE_TZ=True, gravar um datetime ingênuo faz o Django assumir UTC. Como
    Brasília é UTC-3, um show anunciado para 21h era gravado como 21h UTC e
    exibido às 18h. Pior: os filtros de template chamam localtime(), que levanta
    ValueError em datetime ingênuo — a página do evento quebrava.
    """
    if momento is None:
        return None
    if isinstance(momento, datetime) and timezone.is_naive(momento):
        return timezone.make_aware(momento, timezone.get_current_timezone())
    return momento


@dataclass
class EventoImportado:
    """Um evento vindo de uma fonte externa, antes de virar registro no banco."""

    id_externo: str
    nome: str
    data: datetime
    local: str
    link_original: str
    data_fim: datetime | None = None
    endereco: str = ""
    descricao: str = ""
    categoria: str = ""
    organizador: str = ""
    imagem_url: str = ""
    preco: Decimal | None = None
    gratuito: bool = False
    regiao: str = ""
    latitude: float | None = None
    longitude: float | None = None
    cidade: str = "Brasília"
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.data = garantir_aware(self.data)
        self.data_fim = garantir_aware(self.data_fim)

    def valido(self):
        """Sem nome ou sem data real o evento é descartado — nunca inventamos valores."""
        if not (self.id_externo and self.nome and self.data):
            return False
        if self.data_fim and self.data_fim < self.data:
            self.avisos.append("data_fim anterior ao início; descartada")
            self.data_fim = None
        return True

    def regiao_inferida(self):
        if self.regiao in {r.value for r in Regiao}:
            return self.regiao
        alvo = f" {normalizar(f'{self.local} {self.endereco}')} "
        for rotulo, valor in _ROTULOS_REGIAO:
            if not rotulo:
                continue
            chave = rotulo.replace("-", " ")
            if rotulo in _ROTULOS_CURTOS:
                if f" {chave} " in alvo:
                    return valor
            elif chave in alvo:
                return valor
        return ""

    def categoria_normalizada(self):
        chave = slugify(self.categoria)
        return chave if chave in _VALORES_CATEGORIA else ""


def _resolver_local(importado, regiao):
    """Encontra ou cria o Local, deduplicando por nome normalizado."""
    nome = (importado.local or "").strip()[:200]
    if not nome:
        return None
    chave = normalizar(nome)[:200]
    local = Local.objects.filter(nome_normalizado=chave).first()
    if local is None:
        local = Local(
            nome=nome,
            endereco=(importado.endereco or "")[:300],
            regiao=regiao or "",
            cidade=importado.cidade or "Brasília",
        )
        if importado.latitude is not None and importado.longitude is not None:
            local.latitude, local.longitude = importado.latitude, importado.longitude
            local.geocodificado_em = timezone.now()
            local.atualizar_metro()
        local.save()
        return local

    # Local já existente: preenche buracos, nunca sobrescreve o que já tem.
    mudou = []
    if not local.endereco and importado.endereco:
        local.endereco = importado.endereco[:300]
        mudou.append("endereco")
    if not local.regiao and regiao:
        local.regiao = regiao
        mudou.append("regiao")
    if local.latitude is None and importado.latitude is not None:
        local.latitude, local.longitude = importado.latitude, importado.longitude
        local.geocodificado_em = timezone.now()
        local.atualizar_metro()
        mudou += ["latitude", "longitude", "geocodificado_em", "metro_proximo", "metro_distancia_m"]
    if mudou:
        local.save(update_fields=mudou)
    return local


def _resolver_produtor(importado):
    nome = (importado.organizador or "").strip()[:200]
    if not nome:
        return None
    chave = normalizar(nome)[:200]
    produtor = Produtor.objects.filter(nome_normalizado=chave).first()
    if produtor is None:
        produtor = Produtor.objects.create(nome=nome)
    return produtor


@transaction.atomic
def salvar_importados(eventos, fonte, status=None, vincular_entidades=True):
    """Grava de forma idempotente: atualiza o que já existe, cria o resto.

    Nunca apaga registros. Os campos que a fonte publica são atualizados a cada
    execução; os que são decisão do Finde (status, destaque) ou palpite nosso
    (categoria, região) só entram na criação, para não desfazer curadoria.

    `status` padrão é PENDENTE: nada vindo de fora vai ao ar sem alguém olhar.
    Um conector de fonte confiável pode passar PUBLICADO explicitamente.
    """
    status = status or Evento.Status.PENDENTE
    criados = atualizados = ignorados = 0
    avisos = []

    for importado in eventos:
        if not importado.valido():
            ignorados += 1
            logger.warning(
                "Evento descartado por falta de nome ou data: %s", importado.link_original
            )
            continue

        regiao = importado.regiao_inferida()
        local = _resolver_local(importado, regiao) if vincular_entidades else None
        produtor = _resolver_produtor(importado) if vincular_entidades else None

        campos = {
            "nome": importado.nome[:300],
            "data": importado.data,
            "data_fim": importado.data_fim,
            "local": (importado.local[:300] or "A confirmar"),
            "endereco": importado.endereco[:300],
            "descricao": importado.descricao,
            "organizador": importado.organizador[:200],
            "imagem_url": importado.imagem_url[:600],
            "link_original": importado.link_original[:600],
            "gratuito": importado.gratuito,
            "preco": importado.preco,
            "cidade": importado.cidade or "Brasília",
        }
        if local is not None:
            campos["local_ref"] = local
        if produtor is not None:
            campos["produtor"] = produtor

        # Categoria e região saem de heurística, não da fonte. Se um humano
        # corrigiu o palpite no admin, a próxima importação não pode atropelar.
        inferidos = {
            "categoria": importado.categoria_normalizada(),
            "regiao": regiao,
            "status": status,
        }

        evento, criado = Evento.objects.update_or_create(
            fonte=fonte,
            id_externo=importado.id_externo,
            defaults=campos,
            create_defaults={**campos, **inferidos},
        )

        if criado:
            criados += 1
        else:
            atualizados += 1
            vazios = {
                c: v
                for c, v in inferidos.items()
                if c != "status" and v and not getattr(evento, c)
            }
            if vazios:
                for campo, valor in vazios.items():
                    setattr(evento, campo, valor)
                evento.save(update_fields=list(vazios))

        if importado.avisos:
            avisos.extend(f"{importado.id_externo}: {a}" for a in importado.avisos)

    return {
        "criados": criados,
        "atualizados": atualizados,
        "ignorados": ignorados,
        "avisos": avisos,
    }
