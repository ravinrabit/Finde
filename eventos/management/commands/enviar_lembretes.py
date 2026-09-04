"""Lembrete de véspera para quem reservou.

Favorito e ingresso viravam lista morta: ninguém era avisado. Um e-mail na
véspera é o mecanismo de retorno mais barato que existe num site de eventos.
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from eventos import emails
from eventos.models import Favorito, Ingresso


class Command(BaseCommand):
    help = "Envia lembrete dos eventos que acontecem amanhã."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=1)
        parser.add_argument("--simular", action="store_true")
        parser.add_argument(
            "--incluir-favoritos",
            action="store_true",
            help="Avisa também quem só favoritou, sem ter reservado.",
        )
        parser.add_argument("--base-url", default="")

    def handle(self, *args, **opcoes):
        alvo = timezone.localdate() + timedelta(days=opcoes["dias"])
        inicio = timezone.make_aware(
            timezone.datetime.combine(alvo, timezone.datetime.min.time())
        )
        fim = inicio + timedelta(days=1)

        por_usuario = defaultdict(lambda: defaultdict(list))

        for ingresso in (
            Ingresso.objects.filter(
                status=Ingresso.Status.CONFIRMADO, evento__data__gte=inicio, evento__data__lt=fim
            )
            .select_related("evento", "usuario")
        ):
            por_usuario[ingresso.usuario][ingresso.evento].append(ingresso)

        if opcoes["incluir_favoritos"]:
            for favorito in (
                Favorito.objects.filter(evento__data__gte=inicio, evento__data__lt=fim)
                .select_related("evento", "usuario")
            ):
                por_usuario[favorito.usuario].setdefault(favorito.evento, [])

        enviados = 0
        for usuario, eventos in por_usuario.items():
            if not usuario.email:
                continue
            for evento, ingressos in eventos.items():
                if opcoes["simular"]:
                    self.stdout.write(f"  {usuario.email} <- {evento.nome}")
                    continue
                url = f"{opcoes['base_url'].rstrip('/')}{evento.get_absolute_url()}" if opcoes["base_url"] else ""
                if emails.lembrete_de_evento(usuario, evento, ingressos, url):
                    enviados += 1

        rotulo = "simulado(s)" if opcoes["simular"] else "enviado(s)"
        self.stdout.write(self.style.SUCCESS(f"{enviados} lembrete(s) {rotulo} para {alvo:%d/%m/%Y}."))
