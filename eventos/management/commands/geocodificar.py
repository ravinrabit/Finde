from django.core.management.base import BaseCommand

from eventos.constants import Modalidade
from eventos.models import Evento, Local
from eventos.services import geocoding


class Command(BaseCommand):
    help = (
        "Preenche latitude/longitude dos locais via Nominatim/OpenStreetMap, "
        "respeitando 1 requisição por segundo e usando cache de 30 dias."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument(
            "--sem-rede",
            action="store_true",
            help="Não consulta o Nominatim: usa só o centro da região administrativa.",
        )
        parser.add_argument(
            "--refazer-aproximados",
            action="store_true",
            help="Tenta de novo os locais que ficaram com coordenada aproximada.",
        )
        parser.add_argument("--metro", action="store_true", help="Só recalcula a estação de metrô.")
        parser.add_argument(
            "--sem-vincular",
            action="store_true",
            help="Pula a etapa de criar Local para eventos que só têm o nome em texto.",
        )

    def handle(self, *args, **opcoes):
        if opcoes["metro"]:
            return self._so_metro()

        if not opcoes["sem_vincular"]:
            self._vincular_locais()

        if opcoes["refazer_aproximados"]:
            recontar = Local.objects.filter(coordenada_aproximada=True).update(
                latitude=None, longitude=None, geocodificacao_falhou=False
            )
            self.stdout.write(f"{recontar} local(is) aproximado(s) voltaram para a fila.")

        pendentes = Local.objects.pendentes_de_geocodificacao().count()
        self.stdout.write(f"{pendentes} local(is) na fila de geocodificação.")

        def relatar(local, resultado):
            estilo = {
                "exata": self.style.SUCCESS,
                "aproximada": self.style.WARNING,
                "falhou": self.style.ERROR,
            }[resultado]
            self.stdout.write(estilo(f"  {resultado:11s} {local.nome[:55]}"))

        contagem = geocoding.geocodificar_pendentes(
            limite=opcoes["limite"], usar_rede=not opcoes["sem_rede"], ao_processar=relatar
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{contagem['exata']} exata(s), {contagem['aproximada']} aproximada(s), "
                f"{contagem['falhou']} sem coordenada."
            )
        )
        restantes = Local.objects.pendentes_de_geocodificacao().count()
        if restantes:
            self.stdout.write(f"Ainda faltam {restantes}. Rode de novo para continuar a fila.")

    def _vincular_locais(self):
        """Cria o Local dos eventos que só têm o nome do lugar em texto.

        Evento sem local_ref não tem coordenada, e sem coordenada não existe
        para o mapa nem para o "perto de mim". Eventos criados antes desta
        garantia entrar no save() — ou pelo semear_demo, ou por script —
        ficaram nessa situação e precisam ser religados uma vez.
        """
        pendentes = (
            Evento.objects.filter(local_ref__isnull=True)
            .exclude(modalidade=Modalidade.ONLINE)
            .exclude(local="")
        )
        total = pendentes.count()
        if not total:
            return

        self.stdout.write(f"{total} evento(s) sem local cadastrado. Vinculando…")
        antes = Local.objects.count()
        for evento in pendentes.iterator():
            evento.save()  # _garantir_local() faz o vínculo
        criados = Local.objects.count() - antes
        self.stdout.write(
            self.style.SUCCESS(f"  {criados} local(is) criado(s), {total} evento(s) vinculado(s).\n")
        )

    def _so_metro(self):
        atualizados = 0
        for local in Local.objects.com_coordenadas().iterator():
            if local.atualizar_metro():
                local.save(update_fields=["metro_proximo", "metro_distancia_m"])
                atualizados += 1
        self.stdout.write(self.style.SUCCESS(f"{atualizados} local(is) com estação de metrô."))
