"""Fábricas compartilhadas pelos testes novos."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from ..constants import Categoria, Regiao
from ..models import Evento, Local, Produtor


def criar_evento(**campos):
    padrao = {
        "nome": "Show de teste no Cerrado",
        "data": timezone.now() + timedelta(days=5),
        "local": "Clube do Choro",
        "categoria": Categoria.MUSICA,
        "regiao": Regiao.ASA_SUL,
        "preco": Decimal("50.00"),
        "status": Evento.Status.PUBLICADO,
    }
    return Evento.objects.create(**{**padrao, **campos})


def criar_local(**campos):
    padrao = {
        "nome": "Cine Brasília",
        "regiao": Regiao.ASA_SUL,
        "latitude": Decimal("-15.826700"),
        "longitude": Decimal("-47.908900"),
    }
    return Local.objects.create(**{**padrao, **campos})


def criar_produtor(**campos):
    return Produtor.objects.create(**{"nome": "Produtora Cerrado", **campos})


def criar_usuario(email="pessoa@exemplo.test", senha="senha-forte-123"):
    return User.objects.create_user(username=email, email=email, password=senha)
