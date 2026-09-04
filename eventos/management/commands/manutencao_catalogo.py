"""FASE 15 — o que roda sozinho, todo dia.

O importador dependia de alguém lembrar de rodar o comando na mão, o que
significa que a importação "automática" nunca foi automática. Este comando
reúne a rotina diária num alvo só, para o agendador chamar.

Com cron (suficiente para o tamanho atual do projeto):

    # importação e manutenção, 6h da manhã
    0 6 * * *  cd /app && python manage.py manutencao_catalogo >> /var/log/finde-cron.log 2>&1
    # lembretes de eventos do dia seguinte, 10h
    0 10 * * * cd /app && python manage.py enviar_lembretes >> /var/log/finde-cron.log 2>&1
    # limpeza de sessões, domingo de madrugada
    0 3 * * 0  cd /app && python manage.py clearsessions

Com Celery Beat (quando houver worker), a mesma rotina vira uma task periódica
chamando `call_command("manutencao_catalogo")`. Não vale subir broker e worker
só por isto enquanto cron dá conta.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from eventos.models import Evento, Local


class Command(BaseCommand):
    help = "Rotina diária: importa, geocodifica, arquiva o que passou e limpa órfãos."

    def add_arguments(self, parser):
        parser.add_argument("--sem-importar", action="store_true")
        parser.add_argument("--sem-geocodificar", action="store_true")
        parser.add_argument("--dias-para-arquivar", type=int, default=30)

    def handle(self, *args, **opcoes):
        inicio = timezone.now()
        self.stdout.write(self.style.MIGRATE_HEADING(f"Manutenção — {inicio:%d/%m/%Y %H:%M}"))

        if not opcoes["sem_importar"]:
            self.stdout.write("\n[1/4] Importação")
            try:
                call_command("importar_eventos", fonte="todas", limite=300)
            except Exception as erro:
                self.stdout.write(self.style.ERROR(f"  importação falhou: {erro}"))

        if not opcoes["sem_geocodificar"]:
            self.stdout.write("\n[2/4] Geocodificação")
            try:
                call_command("geocodificar")
            except Exception as erro:
                self.stdout.write(self.style.ERROR(f"  geocodificação falhou: {erro}"))

        self.stdout.write("\n[3/4] Arquivamento de eventos vencidos")
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

        self.stdout.write("\n[4/4] Limpeza de órfãos")
        orfaos = (
            Local.objects.annotate(total=Count("eventos"))
            .filter(total=0, criado_em__lt=timezone.now() - timezone.timedelta(days=90))
        )
        quantidade = orfaos.count()
        orfaos.delete()
        self.stdout.write(f"  {quantidade} local(is) sem evento há 90 dias removido(s).")

        duracao = (timezone.now() - inicio).total_seconds()
        self.stdout.write(self.style.SUCCESS(f"\nConcluído em {duracao:.0f}s."))
