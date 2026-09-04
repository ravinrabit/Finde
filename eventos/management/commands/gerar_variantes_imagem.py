"""Gera as versões 400/800/1200 em WebP das capas já enviadas."""

from django.core.management.base import BaseCommand

from eventos.models import Evento, Produtor
from eventos.services import imagens


class Command(BaseCommand):
    help = "Gera thumbnails WebP das capas existentes (uploads antigos não passaram pelo pipeline)."

    def add_arguments(self, parser):
        parser.add_argument("--forcar", action="store_true", help="Regera mesmo se já existir.")
        parser.add_argument("--limite", type=int, default=None)

    def handle(self, *args, **opcoes):
        feitos = 0
        consulta = Evento.objects.exclude(imagem="").order_by("-criado_em")
        if opcoes["limite"]:
            consulta = consulta[: opcoes["limite"]]

        for evento in consulta:
            variantes = imagens.gerar_variantes(evento.imagem, forcar=opcoes["forcar"])
            if variantes:
                feitos += 1
                self.stdout.write(f"  {len(variantes)} variante(s) — {evento.nome[:50]}")

        for produtor in Produtor.objects.exclude(logo=""):
            imagens.gerar_variantes(produtor.logo, larguras=(200, 400), forcar=opcoes["forcar"])

        self.stdout.write(self.style.SUCCESS(f"{feitos} capa(s) processada(s)."))
