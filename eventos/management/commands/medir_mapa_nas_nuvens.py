"""FASE 12 — medir antes de construir.

Nenhuma infraestrutura deve ser construída em cima de uma fonte cujo volume
real ninguém verificou. Este comando responde, com números:

  - quantos eventos futuros a API devolve;
  - quantas ocorrências datadas isso vira;
  - quais campos vêm preenchidos (imagem, local, coordenada, categoria);
  - qual a cobertura por região administrativa;
  - qual o horizonte de datas e quando os registros foram criados.

Depois de rodar, a decisão é objetiva: se o volume sustenta o catálogo, siga
com o conector; se não, adiante os conectores de parceiro e o "colar link".
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.utils import timezone

from eventos.constants import Regiao
from eventos.ingestao import mapa_nas_nuvens
from eventos.ingestao.http import FonteIndisponivel


class Command(BaseCommand):
    help = "Mede o volume e a qualidade da API do Mapa nas Nuvens antes de confiar nela."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=500)
        parser.add_argument("--amostra", type=int, default=5, help="Eventos a exibir por extenso.")

    def handle(self, *args, **opcoes):
        agora = timezone.now()
        self.stdout.write(self.style.MIGRATE_HEADING("MEDIÇÃO — MAPA NAS NUVENS"))
        self.stdout.write(f"Endpoint: {mapa_nas_nuvens._url('/api/event/find/')}")

        try:
            brutos = mapa_nas_nuvens.buscar_bruto(limite=opcoes["limite"], desde=agora.date())
        except FonteIndisponivel as erro:
            self.stdout.write(self.style.ERROR(f"FONTE INDISPONÍVEL: {erro}"))
            self.stdout.write(
                "Sem resposta da API, a Fase 2 do roadmap muda: priorize parceiros e 'colar link'."
            )
            return

        self.stdout.write(f"Eventos retornados pela API: {len(brutos)}")

        ocorrencias, campos = [], Counter()
        regioes, categorias = Counter(), Counter()

        for bruto in brutos:
            achados = mapa_nas_nuvens.para_importados(bruto, agora)
            ocorrencias.extend(achados)
            for importado in achados:
                if importado.imagem_url:
                    campos["imagem"] += 1
                if importado.local and importado.local != "A confirmar":
                    campos["local"] += 1
                if importado.endereco:
                    campos["endereco"] += 1
                if importado.latitude is not None:
                    campos["coordenada"] += 1
                if importado.categoria:
                    campos["categoria"] += 1
                if importado.descricao:
                    campos["descricao"] += 1
                if importado.organizador:
                    campos["organizador"] += 1
                if importado.data_fim:
                    campos["data_fim"] += 1
                regioes[importado.regiao or "(sem região)"] += 1
                categorias[importado.categoria or "(sem categoria)"] += 1

        total = len(ocorrencias)
        self.stdout.write(self.style.SUCCESS(f"\nOCORRÊNCIAS FUTURAS DATADAS: {total}"))
        if not total:
            self.stdout.write(
                self.style.WARNING(
                    "Volume zero. Não construa o catálogo em cima desta fonte agora."
                )
            )
            return

        self.stdout.write("\nPREENCHIMENTO DOS CAMPOS")
        for campo in (
            "local", "endereco", "coordenada", "imagem", "descricao",
            "categoria", "organizador", "data_fim",
        ):
            quantidade = campos[campo]
            self.stdout.write(f"  {campo:14s} {quantidade:5d}  ({quantidade * 100 // total}%)")

        self.stdout.write("\nCOBERTURA POR REGIÃO")
        rotulos = dict(Regiao.choices)
        for valor, quantidade in regioes.most_common(15):
            self.stdout.write(f"  {rotulos.get(valor, valor):22s} {quantidade}")

        self.stdout.write("\nCATEGORIAS INFERIDAS")
        for valor, quantidade in categorias.most_common(10):
            self.stdout.write(f"  {valor:22s} {quantidade}")

        datas = sorted(e.data for e in ocorrencias)
        self.stdout.write("\nHORIZONTE")
        self.stdout.write(f"  primeiro: {datas[0]:%d/%m/%Y}")
        self.stdout.write(f"  último:   {datas[-1]:%d/%m/%Y}")
        proximos_30 = sum(1 for d in datas if (d - agora).days <= 30)
        self.stdout.write(f"  nos próximos 30 dias: {proximos_30}")

        self.stdout.write("\nAMOSTRA")
        for importado in ocorrencias[: opcoes["amostra"]]:
            self.stdout.write(
                f"  {importado.data:%d/%m %H:%M}  {importado.nome[:55]}\n"
                f"      local: {importado.local[:50]} | região: {importado.regiao or '—'} | "
                f"coord: {'sim' if importado.latitude is not None else 'não'}"
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\nLEITURA DO RESULTADO"))
        if proximos_30 >= 60:
            self.stdout.write(
                self.style.SUCCESS(
                    "Volume suficiente para sustentar a home. Siga com o conector como fonte primária."
                )
            )
        elif proximos_30 >= 20:
            self.stdout.write(
                self.style.WARNING(
                    "Volume parcial. Serve como uma das fontes, não como a única. "
                    "Adiante os conectores de parceiro."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Volume insuficiente. Priorize parceiros, 'colar link' e curadoria manual "
                    "antes de desligar qualquer fonte existente."
                )
            )
