from django.core.management.base import BaseCommand
from django.utils import timezone

from eventos.models import Local

# Coordenadas confirmadas manualmente contra o Nominatim/OpenStreetMap antes
# do endereço ruim do backup (região/CEP errados) atrapalhar a busca automática.
COORDENADAS_CONFIRMADAS = {
    "Parque da Cidade Sarah Kubitschek": (-15.7998476, -47.9070091),
    "Arena BRB Mané Garrincha": (-15.7835471, -47.8993690),
    "Teatro Brasília Shopping": (-15.7862278, -47.8891941),
    "UNIPAZ": (-15.9211729, -47.9860046),
    "Galpão 17": (-15.8157285, -47.9660813),
    "Praça do Buriti": (-15.7855811, -47.9084700),
    "Hop Capital Beer": (-15.7993618, -47.9596314),
    "Casa do Candango": (-15.8111088, -47.8836495),
    "IDP": (-15.8215910, -47.8946665),
    "MGRA Brasília": (-15.8744997, -48.0769782),
    "DNOCS": (-15.6637302, -47.7987307),
}


class Command(BaseCommand):
    help = "Aplica coordenadas confirmadas manualmente para locais do backup importado."

    def handle(self, *args, **opcoes):
        atualizados = 0
        for nome, (lat, lon) in COORDENADAS_CONFIRMADAS.items():
            linhas = Local.objects.filter(nome=nome).update(
                latitude=lat,
                longitude=lon,
                coordenada_aproximada=False,
                geocodificacao_falhou=False,
                geocodificado_em=timezone.now(),
            )
            if linhas:
                atualizados += linhas
                self.stdout.write(f"Coordenada aplicada: {nome}")

        self.stdout.write(self.style.SUCCESS(f"{atualizados} local(is) atualizado(s)."))
