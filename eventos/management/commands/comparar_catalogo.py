"""FASE 14 — a régua para decidir se o Selenium já pode sair.

Mostra o volume de eventos futuros por fonte. O importador legado só deve ser
removido quando as fontes legítimas sustentarem o catálogo sozinhas.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from eventos.models import Evento

FONTES_LEGITIMAS = {"manual", "usuario", "produtor", "mapa-df", "parceiros", "sympla-produtor", "ics-avulso"}
FONTES_LEGADAS = {"sympla", "sympla-legado"}


class Command(BaseCommand):
    help = "Compara o volume do catálogo por fonte e diz se dá para desligar o Selenium."

    def handle(self, *args, **opcoes):
        visiveis = Evento.objects.visiveis()
        total = visiveis.count()
        por_fonte = dict(
            visiveis.values_list("fonte").annotate(n=Count("id")).values_list("fonte", "n")
        )

        self.stdout.write(self.style.MIGRATE_HEADING("CATÁLOGO VISÍVEL POR FONTE"))
        for fonte, quantidade in sorted(por_fonte.items(), key=lambda p: -p[1]):
            marca = "  (legado)" if fonte in FONTES_LEGADAS else ""
            fatia = quantidade * 100 // total if total else 0
            self.stdout.write(f"  {fonte:18s} {quantidade:5d}  {fatia:3d}%{marca}")
        self.stdout.write(f"  {'TOTAL':18s} {total:5d}")

        legado = sum(q for f, q in por_fonte.items() if f in FONTES_LEGADAS)
        legitimo = total - legado

        proximos = visiveis.filter(
            data__lte=timezone.now() + timezone.timedelta(days=30)
        ).exclude(fonte__in=FONTES_LEGADAS).count()

        self.stdout.write(self.style.MIGRATE_HEADING("\nVEREDITO"))
        self.stdout.write(f"  eventos de fontes legítimas: {legitimo}")
        self.stdout.write(f"  desses, nos próximos 30 dias: {proximos}")
        self.stdout.write(f"  ainda dependentes do scraper: {legado}")

        if legado == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nNada depende mais do Selenium. Siga o roteiro de remoção no README."
                )
            )
        elif proximos >= 60:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nAs fontes legítimas já sustentam a home. Pode desligar o Selenium "
                    "(SYMPLA_SCRAPING_ATIVO=False já é o padrão) e remover o código."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\nAinda não. Com {proximos} evento(s) nos próximos 30 dias vindos de fontes "
                    "legítimas, desligar agora deixaria a home vazia. Amplie parceiros e produtores."
                )
            )
