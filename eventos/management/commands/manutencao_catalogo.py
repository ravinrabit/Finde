from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from eventos.models import Evento, Local


class Command(BaseCommand):
    help = "Rotina diária: geocodifica, arquiva o que passou e limpa órfãos."

    def add_arguments(self, parser):
        parser.add_argument("--sem-geocodificar", action="store_true")
        parser.add_argument("--dias-para-arquivar", type=int, default=30)

    def handle(self, *args, **opcoes):
        inicio = timezone.now()
        self.stdout.write(self.style.MIGRATE_HEADING(f"Manutenção — {inicio:%d/%m/%Y %H:%M}"))

        if not opcoes["sem_geocodificar"]:
            self.stdout.write("\n[1/3] Geocodificação")
            try:
                call_command("geocodificar")
            except Exception as erro:
                self.stdout.write(self.style.ERROR(f"  geocodificação falhou: {erro}"))

        self.stdout.write("\n[2/3] Arquivamento de eventos vencidos")
        corte = timezone.now() - timezone.timedelta(days=opcoes["dias_para_arquivar"])
        arquivados = (
            Evento.objects.filter(status=Evento.Status.PUBLICADO)
            .filter(data__lt=corte)
            .exclude(data_fim__gte=corte)
            .update(status=Evento.Status.ARQUIVADO)
        )
        self.stdout.write(f"  {arquivados} evento(s) arquivado(s).")

        pendentes_velhos = Evento.objects.filter(
            status=Evento.Status.PENDENTE, data__lt=timezone.now()
        ).update(status=Evento.Status.ARQUIVADO)
        self.stdout.write(f"  {pendentes_velhos} pendente(s) vencido(s) arquivado(s).")

        self.stdout.write("\n[3/3] Limpeza de órfãos")
        orfaos = (
            Local.objects.annotate(total=Count("eventos"))
            .filter(total=0, criado_em__lt=timezone.now() - timezone.timedelta(days=90))
        )
        quantidade = orfaos.count()
        orfaos.delete()
        self.stdout.write(f"  {quantidade} local(is) sem evento há 90 dias removido(s).")

        duracao = (timezone.now() - inicio).total_seconds()
        self.stdout.write(self.style.SUCCESS(f"\nConcluído em {duracao:.0f}s."))
