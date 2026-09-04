from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from eventos.ingestao import salvar_importados
from eventos.ingestao import ics as ics_conector
from eventos.ingestao import mapa_nas_nuvens, parceiros, sympla_api
from eventos.models import Evento

FONTES = {
    "mapa-df": mapa_nas_nuvens.coletar,
    "parceiros": parceiros.coletar,
    "sympla-produtor": sympla_api.coletar,
}


def _sympla_legado(**kwargs):
    from eventos.ingestao import sympla

    return sympla.coletar(**kwargs)


FONTES["sympla-legado"] = _sympla_legado


class Command(BaseCommand):
    help = (
        "Importa eventos de fontes externas para o catálogo, de forma idempotente. "
        "Tudo entra como PENDENTE e passa pela fila de curadoria."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fonte",
            default="mapa-df",
            choices=sorted(FONTES) + ["todas"],
            help="Fonte a importar. 'todas' percorre as fontes legítimas.",
        )
        parser.add_argument("--limite", type=int, default=200, help="Máximo de eventos por fonte.")
        parser.add_argument("--simular", action="store_true", help="Coleta e exibe sem gravar.")
        parser.add_argument(
            "--publicar",
            action="store_true",
            help="Grava já publicado. Use apenas em fonte de confiança comprovada.",
        )
        parser.add_argument("--ics", help="URL de um feed .ics avulso a importar.")
        parser.add_argument("--com-janela", action="store_true", help="[legado] abre o navegador.")

    def handle(self, *args, **opcoes):
        inicio = timezone.now()
        status = Evento.Status.PUBLICADO if opcoes["publicar"] else Evento.Status.PENDENTE

        if opcoes["ics"]:
            return self._importar(
                "ics-avulso",
                lambda **k: ics_conector.coletar(opcoes["ics"], **k),
                opcoes,
                status,
                inicio,
            )

        alvos = ["mapa-df", "parceiros", "sympla-produtor"] if opcoes["fonte"] == "todas" else [opcoes["fonte"]]
        total = {"criados": 0, "atualizados": 0, "ignorados": 0}
        for nome in alvos:
            parcial = self._importar(nome, FONTES[nome], opcoes, status, inicio)
            for chave in total:
                total[chave] += parcial.get(chave, 0)

        if len(alvos) > 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"TOTAL: {total['criados']} criado(s), {total['atualizados']} atualizado(s), "
                    f"{total['ignorados']} ignorado(s)."
                )
            )

    def _importar(self, nome, coletar, opcoes, status, inicio):
        self.stdout.write(f"Importando de {nome} (limite {opcoes['limite']})…")
        try:
            eventos = list(
                coletar(limite=opcoes["limite"], headless=not opcoes["com_janela"])
            )
        except TypeError:
            eventos = list(coletar(limite=opcoes["limite"]))
        except RuntimeError as erro:
            raise CommandError(str(erro)) from erro

        if opcoes["simular"]:
            for evento in eventos:
                self.stdout.write(
                    f"  {evento.data:%d/%m/%Y %H:%M}  {evento.nome[:60]}  ({evento.local[:40]})"
                )
            self.stdout.write(
                self.style.WARNING(f"Simulação: {len(eventos)} evento(s), nada foi gravado.")
            )
            return {}

        resultado = salvar_importados(eventos, fonte=nome, status=status)
        duracao = (timezone.now() - inicio).total_seconds()
        rotulo = "publicado(s)" if status == Evento.Status.PUBLICADO else "na fila de curadoria"
        self.stdout.write(
            self.style.SUCCESS(
                f"  {nome}: {resultado['criados']} criado(s) {rotulo}, "
                f"{resultado['atualizados']} atualizado(s), "
                f"{resultado['ignorados']} ignorado(s) em {duracao:.0f}s."
            )
        )
        for aviso in resultado.get("avisos", [])[:10]:
            self.stdout.write(self.style.WARNING(f"    aviso: {aviso}"))
        return resultado
