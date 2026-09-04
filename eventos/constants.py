import unicodedata

from django.db import models


class Categoria(models.TextChoices):
    SHOWS = "shows", "Shows"
    FESTAS = "festas", "Festas"
    MUSICA = "musica", "Música"
    FESTIVAIS = "festivais", "Festivais"
    TEATRO = "teatro", "Teatro"
    CINEMA = "cinema", "Cinema"
    CULTURA = "cultura", "Cultura"
    GASTRONOMIA = "gastronomia", "Gastronomia"
    ESPORTES = "esportes", "Esportes"
    TECNOLOGIA = "tecnologia", "Tecnologia"
    NEGOCIOS = "negocios", "Negócios"
    NETWORKING = "networking", "Networking"
    EDUCACAO = "educacao", "Educação"
    WORKSHOPS = "workshops", "Workshops"
    CURSOS = "cursos", "Cursos"
    EXPOSICOES = "exposicoes", "Exposições"
    ARTE = "arte", "Arte"
    INFANTIL = "infantil", "Infantil"
    FAMILIA = "familia", "Família"
    RELIGIOSO = "religioso", "Religioso"
    CORPORATIVO = "corporativo", "Corporativo"
    # O valor era "universitário" (com acento). Como slugify() nunca produz
    # acento, nenhum evento importado conseguia cair nesta categoria.
    # A migration 0010 reescreve os registros antigos.
    UNIVERSITARIO = "universitario", "Universitário"
    AR_LIVRE = "ar-livre", "Ar livre"
    OUTROS = "outros", "Outros"


ICONE_POR_CATEGORIA = {
    Categoria.SHOWS: "microfone",
    Categoria.FESTAS: "taca",
    Categoria.MUSICA: "nota",
    Categoria.FESTIVAIS: "estrela",
    Categoria.TEATRO: "mascara",
    Categoria.CINEMA: "claquete",
    Categoria.CULTURA: "livro",
    Categoria.GASTRONOMIA: "prato",
    Categoria.ESPORTES: "bola",
    Categoria.TECNOLOGIA: "chip",
    Categoria.NEGOCIOS: "pasta",
    Categoria.NETWORKING: "pessoas",
    Categoria.EDUCACAO: "livro",
    Categoria.WORKSHOPS: "ferramenta",
    Categoria.CURSOS: "livro",
    Categoria.EXPOSICOES: "quadro",
    Categoria.ARTE: "pincel",
    Categoria.INFANTIL: "balao",
    Categoria.FAMILIA: "pessoas",
    Categoria.RELIGIOSO: "vela",
    Categoria.CORPORATIVO: "pasta",
    Categoria.UNIVERSITARIO: "capelo",
    Categoria.AR_LIVRE: "arvore",
    Categoria.OUTROS: "ingresso",
}

ICONE_PADRAO = "ingresso"


class Regiao(models.TextChoices):
    PLANO_PILOTO = "plano-piloto", "Plano Piloto"
    ASA_SUL = "asa-sul", "Asa Sul"
    ASA_NORTE = "asa-norte", "Asa Norte"
    LAGO_SUL = "lago-sul", "Lago Sul"
    LAGO_NORTE = "lago-norte", "Lago Norte"
    SUDOESTE = "sudoeste", "Sudoeste/Octogonal"
    NOROESTE = "noroeste", "Noroeste"
    CRUZEIRO = "cruzeiro", "Cruzeiro"
    AGUAS_CLARAS = "aguas-claras", "Águas Claras"
    TAGUATINGA = "taguatinga", "Taguatinga"
    CEILANDIA = "ceilandia", "Ceilândia"
    GUARA = "guara", "Guará"
    SAMAMBAIA = "samambaia", "Samambaia"
    VICENTE_PIRES = "vicente-pires", "Vicente Pires"
    SOBRADINHO = "sobradinho", "Sobradinho"
    PLANALTINA = "planaltina", "Planaltina"
    GAMA = "gama", "Gama"
    SANTA_MARIA = "santa-maria", "Santa Maria"
    RECANTO_DAS_EMAS = "recanto-das-emas", "Recanto das Emas"
    RIACHO_FUNDO = "riacho-fundo", "Riacho Fundo"
    NUCLEO_BANDEIRANTE = "nucleo-bandeirante", "Núcleo Bandeirante"
    PARK_WAY = "park-way", "Park Way"
    JARDIM_BOTANICO = "jardim-botanico", "Jardim Botânico"
    SAO_SEBASTIAO = "sao-sebastiao", "São Sebastião"
    PARANOA = "paranoa", "Paranoá"
    BRAZLANDIA = "brazlandia", "Brazlândia"
    ENTORNO = "entorno", "Entorno do DF"
    ONLINE = "online", "Online"


# Regiões destacadas na home. As demais continuam disponíveis nos filtros.
REGIOES_EM_DESTAQUE = [
    Regiao.PLANO_PILOTO,
    Regiao.ASA_NORTE,
    Regiao.ASA_SUL,
    Regiao.AGUAS_CLARAS,
    Regiao.TAGUATINGA,
    Regiao.LAGO_SUL,
    Regiao.SUDOESTE,
    Regiao.CEILANDIA,
]


class Modalidade(models.TextChoices):
    PRESENCIAL = "presencial", "Presencial"
    ONLINE = "online", "Online"
    HIBRIDO = "hibrido", "Híbrido"


PERIODOS = [
    ("hoje", "Hoje"),
    ("amanha", "Amanhã"),
    ("fim-de-semana", "Fim de semana"),
    ("semana", "Próximos 7 dias"),
    ("mes", "Próximos 30 dias"),
]

PRECOS = [
    ("gratuito", "Gratuito"),
    ("ate-50", "Até R$ 50"),
    ("50-150", "R$ 50 a R$ 150"),
    ("acima-150", "Acima de R$ 150"),
]

ORDENACOES = [
    ("data", "Data mais próxima"),
    ("preco", "Menor preço"),
    ("recentes", "Adicionados recentemente"),
    ("distancia", "Mais perto de mim"),
]

RAIOS = [
    ("1", "Até 1 km"),
    ("2", "Até 2 km"),
    ("5", "Até 5 km"),
    ("10", "Até 10 km"),
    ("20", "Até 20 km"),
]

ACESSOS = [
    ("acessivel", "Acessível para cadeirante"),
    ("metro", "Perto do metrô"),
    ("estacionamento", "Com estacionamento"),
]


def normalizar(texto):
    """Minúsculas, sem acento, espaços colapsados.

    É a base de tudo que precisa comparar texto de forma tolerante: busca,
    deduplicação de locais e produtores, inferência de região. Uma função só
    para que busca e deduplicação nunca divirjam.
    """
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


# Texto editorial por categoria. Alimenta /eventos/categoria/<slug>/, que sem
# conteúdo próprio viraria 24 páginas duplicadas aos olhos do Google.
DESCRICAO_POR_CATEGORIA = {
    Categoria.SHOWS: "Shows e apresentações musicais no Distrito Federal, do Mané Garrincha aos palcos de bairro.",
    Categoria.FESTAS: "Festas, baladas e encontros noturnos em Brasília e nas cidades do DF.",
    Categoria.MUSICA: "Música ao vivo em Brasília: choro, samba, rock, MPB, erudita e o que a cidade inventar.",
    Categoria.FESTIVAIS: "Festivais de música, cinema, gastronomia e cultura no Distrito Federal.",
    Categoria.TEATRO: "Teatro em Brasília: temporadas, estreias e mostras nos palcos do DF.",
    Categoria.CINEMA: "Sessões, mostras e festivais de cinema no Distrito Federal.",
    Categoria.CULTURA: "Programação cultural do DF: saraus, rodas, lançamentos e encontros.",
    Categoria.GASTRONOMIA: "Feiras, festivais e experiências gastronômicas em Brasília e no DF.",
    Categoria.ESPORTES: "Corridas, torneios e eventos esportivos no Distrito Federal.",
    Categoria.TECNOLOGIA: "Meetups, hackathons e eventos de tecnologia em Brasília.",
    Categoria.NEGOCIOS: "Eventos de negócios, empreendedorismo e mercado no DF.",
    Categoria.NETWORKING: "Encontros de networking e comunidades profissionais em Brasília.",
    Categoria.EDUCACAO: "Palestras, aulas abertas e eventos educacionais no Distrito Federal.",
    Categoria.WORKSHOPS: "Workshops e oficinas práticas em Brasília e no DF.",
    Categoria.CURSOS: "Cursos livres, intensivos e formações no Distrito Federal.",
    Categoria.EXPOSICOES: "Exposições e mostras em museus, galerias e centros culturais do DF.",
    Categoria.ARTE: "Artes visuais, dança e performance na cena do Distrito Federal.",
    Categoria.INFANTIL: "Programação para crianças em Brasília: teatro, oficinas e brincadeiras.",
    Categoria.FAMILIA: "Programas para levar a família toda, no Plano e nas cidades do DF.",
    Categoria.RELIGIOSO: "Encontros, celebrações e eventos religiosos no Distrito Federal.",
    Categoria.CORPORATIVO: "Congressos, convenções e eventos corporativos em Brasília.",
    Categoria.UNIVERSITARIO: "A agenda universitária do DF: UnB, UCB, IESB, UDF e o que rola nos campi.",
    Categoria.AR_LIVRE: "Eventos ao ar livre no DF: parques, orla do Paranoá, Eixão e praças.",
    Categoria.OUTROS: "O que não cabe nas outras categorias, mas acontece em Brasília.",
}

DESCRICAO_POR_REGIAO = {
    Regiao.CEILANDIA: "A maior cidade do DF tem cena própria: Casa do Cantador, hip hop, teatro e feira.",
    Regiao.TAGUATINGA: "Praça do Relógio, shoppings e uma agenda que não depende do Plano Piloto.",
    Regiao.PLANO_PILOTO: "Esplanada, Setor Cultural, Parque da Cidade e os grandes equipamentos da capital.",
    Regiao.ASA_NORTE: "Cine Brasília, bares de quadra, UnB e a programação universitária da cidade.",
    Regiao.ASA_SUL: "Clube do Choro, teatros e a vida cultural das quadras do sul.",
    Regiao.AGUAS_CLARAS: "Uma das RAs que mais cresce, com agenda própria e fácil acesso pelo metrô.",
    Regiao.GAMA: "Programação do sul do DF, com forte presença de cultura popular e esporte.",
    Regiao.SAMAMBAIA: "Cena cultural em expansão, servida pelas estações do metrô.",
    Regiao.PLANALTINA: "A cidade mais antiga do DF, com Complexo Cultural e tradição de festas populares.",
    Regiao.SOBRADINHO: "Programação do norte do DF, entre serra, música e feiras.",
    Regiao.GUARA: "Feira do Guará, teatro e uma das agendas mais constantes fora do Plano.",
}

# Centro aproximado de cada RA. Fallback quando a geocodificação por endereço
# falha, e centro do mapa nas páginas de faceta.
CENTROIDE_POR_REGIAO = {
    Regiao.PLANO_PILOTO: (-15.7939, -47.8828),
    Regiao.ASA_SUL: (-15.8267, -47.9089),
    Regiao.ASA_NORTE: (-15.7601, -47.8790),
    Regiao.LAGO_SUL: (-15.8419, -47.8542),
    Regiao.LAGO_NORTE: (-15.7333, -47.8333),
    Regiao.SUDOESTE: (-15.7950, -47.9250),
    Regiao.NOROESTE: (-15.7472, -47.9047),
    Regiao.CRUZEIRO: (-15.7917, -47.9333),
    Regiao.AGUAS_CLARAS: (-15.8344, -48.0300),
    Regiao.TAGUATINGA: (-15.8333, -48.0578),
    Regiao.CEILANDIA: (-15.8175, -48.1075),
    Regiao.GUARA: (-15.8256, -47.9819),
    Regiao.SAMAMBAIA: (-15.8756, -48.0844),
    Regiao.VICENTE_PIRES: (-15.8028, -48.0361),
    Regiao.SOBRADINHO: (-15.6533, -47.7908),
    Regiao.PLANALTINA: (-15.6178, -47.6528),
    Regiao.GAMA: (-16.0208, -48.0644),
    Regiao.SANTA_MARIA: (-16.0083, -48.0181),
    Regiao.RECANTO_DAS_EMAS: (-15.9000, -48.0583),
    Regiao.RIACHO_FUNDO: (-15.8833, -48.0167),
    Regiao.NUCLEO_BANDEIRANTE: (-15.8697, -47.9700),
    Regiao.PARK_WAY: (-15.8833, -47.9500),
    Regiao.JARDIM_BOTANICO: (-15.8697, -47.8117),
    Regiao.SAO_SEBASTIAO: (-15.9017, -47.7797),
    Regiao.PARANOA: (-15.7714, -47.7803),
    Regiao.BRAZLANDIA: (-15.6706, -48.2011),
}

CENTRO_DF = (-15.7939, -47.8828)

# Estações do Metrô-DF, para calcular Local.metro_proximo.
# Coordenadas aproximadas (4 casas ≈ 11 m). Conferir antes de usar em produção.
ESTACOES_METRO_DF = [
    ("Central", -15.7936, -47.8825),
    ("Galeria", -15.7975, -47.8878),
    ("102 Sul", -15.8047, -47.8933),
    ("108 Sul", -15.8114, -47.8983),
    ("112 Sul", -15.8186, -47.9036),
    ("114 Sul", -15.8236, -47.9086),
    ("Asa Sul", -15.8281, -47.9147),
    ("Terminal Asa Sul", -15.8342, -47.9214),
    ("Concessionárias", -15.8281, -47.9358),
    ("Feira do Guará", -15.8264, -47.9578),
    ("Guará", -15.8258, -47.9739),
    ("Arniqueiras", -15.8425, -48.0069),
    ("Águas Claras", -15.8347, -48.0236),
    ("Estrada Parque", -15.8339, -48.0433),
    ("Praça do Relógio", -15.8283, -48.0553),
    ("Centro Metropolitano", -15.8175, -48.0619),
    ("Ceilândia Norte", -15.8022, -48.1136),
    ("Ceilândia Centro", -15.8158, -48.1122),
    ("Ceilândia Sul", -15.8322, -48.1119),
    ("Guariroba", -15.8394, -48.1200),
    ("Terminal Ceilândia", -15.8161, -48.1069),
    ("Taguatinga Sul", -15.8506, -48.0569),
    ("Furnas", -15.8686, -48.0736),
    ("Samambaia", -15.8619, -48.0692),
    ("Samambaia Sul", -15.8797, -48.0847),
    ("Terminal Samambaia", -15.8850, -48.0925),
]

METRO_RAIO_PADRAO_M = 1000
