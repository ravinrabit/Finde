import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

ESQUEMAS_URL_PERMITIDOS = {"http", "https"}


def url_segura(valor):
    if not valor:
        return ""
    partes = urllib.parse.urlsplit(valor)
    if partes.scheme.lower() not in ESQUEMAS_URL_PERMITIDOS or not partes.netloc:
        return ""
    return valor


def garantir_aware(momento):
    if momento is None:
        return None
    if isinstance(momento, datetime) and timezone.is_naive(momento):
        return timezone.make_aware(momento, timezone.get_current_timezone())
    return momento


@dataclass
class EventoImportado:
    id_externo: str
    nome: str
    data: datetime
    local: str
    link_original: str
    data_fim: datetime | None = None
    endereco: str = ""
    descricao: str = ""
    organizador: str = ""
    imagem_url: str = ""
    preco: Decimal | None = None
    gratuito: bool = False
    latitude: float | None = None
    longitude: float | None = None
    cidade: str = "Brasília"
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.data = garantir_aware(self.data)
        self.data_fim = garantir_aware(self.data_fim)
        self.link_original = url_segura(self.link_original)
        self.imagem_url = url_segura(self.imagem_url)
