import json
from decimal import Decimal
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from eventos.models import Evento, Local, Produtor

CAMINHO_DADOS = Path(__file__).parent / "_dados_backup_eventos.json"


def _data_local(texto):
    # O backup guarda os horários sem fuso (hora local de Brasília já
    # implícita). make_aware evita depender do comportamento implícito do
    # Django ao salvar um datetime ingênuo.
    if not texto:
        return None
    bruto = parse_datetime(texto)
    return timezone.make_aware(bruto) if timezone.is_naive(bruto) else bruto


class Command(BaseCommand):
    help = (
        "Importa produtores, locais e eventos reais de um backup antigo "
        "(_dados_backup_eventos.json). Idempotente por id_externo/nome — "
        "seguro rodar mais de uma vez ou deixar no comando de build."
    )

    def handle(self, *args, **opcoes):
        if not CAMINHO_DADOS.exists():
            self.stdout.write("Arquivo de backup não encontrado, nada a importar.")
            return

        dados = json.loads(CAMINHO_DADOS.read_text(encoding="utf-8"))

        produtor_por_nome = {}
        for p in dados["produtores"]:
            usuario = None
            if p["usuario_email"]:
                usuario, _ = User.objects.get_or_create(
                    username=p["usuario_email"], defaults={"email": p["usuario_email"]}
                )
            produtor, criado = Produtor.objects.get_or_create(
                nome=p["nome"],
                defaults={
                    "bio": p["bio"],
                    "email": p["email"],
                    "site": p["site"],
                    "instagram": p["instagram"],
                    "whatsapp": p["whatsapp"],
                    "verificado": p["verificado"],
                    "user": usuario,
                },
            )
            produtor_por_nome[p["nome"]] = produtor
            if criado:
                self.stdout.write(f"Produtor criado: {p['nome']}")

        local_por_nome = {}
        for l in dados["locais"]:
            local, criado = Local.objects.get_or_create(
                nome=l["nome"],
                defaults={
                    "endereco": l["endereco"],
                    "referencia": l["referencia"],
                    "regiao": l["regiao"],
                    "cidade": l["cidade"],
                    "cep": l["cep"],
                    "descricao": l["descricao"],
                    "site": l["site"],
                    "latitude": l["latitude"],
                    "longitude": l["longitude"],
                    "acessivel_cadeirante": l["acessivel_cadeirante"],
                    "estacionamento": l["estacionamento"],
                },
            )
            local_por_nome[l["nome"]] = local
            if criado:
                self.stdout.write(f"Local criado: {l['nome']}")

        criados = 0
        for e in dados["eventos"]:
            if Evento.objects.filter(id_externo=e["id_externo_backup"]).exists():
                continue

            Evento.objects.create(
                nome=e["nome"],
                descricao=e["descricao"],
                resumo=e["resumo"],
                data=_data_local(e["data"]),
                data_fim=_data_local(e["data_fim"]),
                modalidade=e["modalidade"],
                local=e["local"],
                local_ref=local_por_nome.get(e["local_nome_ref"]),
                endereco=e["endereco"],
                regiao=e["regiao"],
                cidade=e["cidade"],
                categoria=e["categoria"],
                gratuito=e["gratuito"],
                preco=Decimal(e["preco"]) if e["preco"] is not None else None,
                organizador=e["organizador"],
                produtor=produtor_por_nome.get(e["produtor_nome"]),
                link_ingressos=e["link_ingressos"],
                link_original=e["link_original"],
                fonte="backup",
                id_externo=e["id_externo_backup"],
                status=e["status"],
            )
            criados += 1

        self.stdout.write(self.style.SUCCESS(f"{criados} evento(s) novo(s) importado(s) do backup."))
