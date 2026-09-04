from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from eventos.constants import Categoria, Modalidade, Regiao
from eventos.models import Evento

AVISO = "Evento fictício, criado apenas para demonstrar a interface em ambiente de desenvolvimento."

# (nome, categoria, região, local, dias a partir de hoje, hora, preço, duração em horas)
CATALOGO = [
    ("Cerrado em Concerto: Orquestra Sinfônica Fictícia", Categoria.MUSICA, Regiao.PLANO_PILOTO,
     "Teatro Nacional Cláudio Santoro", 2, 20, Decimal("80.00"), 2),
    ("Choro na Quadra — edição de demonstração", Categoria.MUSICA, Regiao.ASA_SUL,
     "Clube do Choro", 4, 21, Decimal("45.00"), 3),
    ("Festival Exemplo de Cinema Candango", Categoria.CINEMA, Regiao.ASA_NORTE,
     "Cine Brasília", 6, 19, None, 4),
    ("Feira Fictícia de Gastronomia do Cerrado", Categoria.GASTRONOMIA, Regiao.PARK_WAY,
     "Parque de Exposições", 3, 11, None, 8),
    ("Mostra de Arte Demonstrativa", Categoria.EXPOSICOES, Regiao.PLANO_PILOTO,
     "Museu Nacional da República", 1, 10, None, 9),
    ("Corrida Teste do Lago", Categoria.ESPORTES, Regiao.LAGO_SUL,
     "Orla do Lago Paranoá", 9, 7, Decimal("120.00"), 3),
    ("Encontro Fictício de Tecnologia do DF", Categoria.TECNOLOGIA, Regiao.AGUAS_CLARAS,
     "Centro de Convenções de Águas Claras", 12, 9, Decimal("150.00"), 9),
    ("Workshop Exemplo de Fotografia Noturna", Categoria.WORKSHOPS, Regiao.SUDOESTE,
     "Espaço Cultural de Demonstração", 5, 18, Decimal("90.00"), 3),
    ("Sarau de Teste na Ceilândia", Categoria.CULTURA, Regiao.CEILANDIA,
     "Centro Cultural de Demonstração", 2, 19, None, 3),
    ("Peça Fictícia: O Planalto Invisível", Categoria.TEATRO, Regiao.ASA_NORTE,
     "Teatro de Demonstração", 8, 20, Decimal("60.00"), 2),
    ("Festa Demonstrativa de Aniversário da Cidade", Categoria.FESTAS, Regiao.TAGUATINGA,
     "Praça de Eventos Fictícia", 14, 22, Decimal("70.00"), 6),
    ("Domingo Fictício no Parque", Categoria.FAMILIA, Regiao.PLANO_PILOTO,
     "Parque da Cidade Sarah Kubitschek", 6, 9, None, 6),
    ("Meetup Exemplo de Produto Digital", Categoria.NETWORKING, Regiao.NOROESTE,
     "Coworking de Demonstração", 10, 19, None, 3),
    ("Ensaio Aberto Fictício de Dança", Categoria.ARTE, Regiao.GUARA,
     "Galpão Cultural de Demonstração", 7, 17, None, 2),
    ("Palestra Online de Demonstração", Categoria.EDUCACAO, Regiao.ONLINE,
     "Transmissão online", 5, 20, None, 2),
    ("Torneio Fictício de Vôlei de Praia", Categoria.ESPORTES, Regiao.LAGO_NORTE,
     "Arena Esportiva de Demonstração", 16, 8, Decimal("35.00"), 8),
]


class Command(BaseCommand):
    help = "Cria eventos fictícios para desenvolvimento. Não use em produção."

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true", help="Remove os eventos de demonstração.")

    def handle(self, *args, **opcoes):
        if opcoes["limpar"]:
            removidos, _ = Evento.objects.filter(fonte="demo").delete()
            self.stdout.write(self.style.SUCCESS(f"{removidos} registro(s) de demonstração removido(s)."))
            return

        agora = timezone.localtime()
        criados = 0

        for indice, (nome, categoria, regiao, local, dias, hora, preco, duracao) in enumerate(CATALOGO):
            inicio = (agora + timedelta(days=dias)).replace(
                hour=hora, minute=0, second=0, microsecond=0
            )
            gratuito = preco is None
            online = regiao == Regiao.ONLINE

            _, criado = Evento.objects.update_or_create(
                fonte="demo",
                id_externo=f"demo-{indice}",
                defaults={
                    "nome": nome,
                    "resumo": f"Programação de demonstração em {local}.",
                    "descricao": (
                        f"{AVISO}\n\n"
                        f"Os dados desta página são de mentira e servem para testar a listagem, "
                        f"os filtros e a página de detalhe do catálogo. Nada aqui corresponde a um "
                        f"evento real em Brasília."
                    ),
                    "data": inicio,
                    "data_fim": inicio + timedelta(hours=duracao),
                    "modalidade": Modalidade.ONLINE if online else Modalidade.PRESENCIAL,
                    "local": local,
                    "endereco": "" if online else "Endereço de demonstração",
                    "regiao": regiao,
                    "cidade": "Brasília",
                    "categoria": categoria,
                    "gratuito": gratuito,
                    "preco": preco,
                    "organizador": "Organizador de Demonstração",
                    "destaque": indice < 3,
                    "status": Evento.Status.PUBLICADO,
                },
            )
            criados += int(criado)

        self.stdout.write(
            self.style.SUCCESS(
                f"{criados} evento(s) criado(s), {len(CATALOGO) - criados} atualizado(s). "
                "Remova depois com: python manage.py semear_demo --limpar"
            )
        )
