"""Transforma texto livre em entidades, sem apagar nada.

- "Cine Brasília", "Cine Brasilia" e "  cine   brasília " viram UM Local.
- Cada organizador distinto vira um Produtor.
- Preenche busca_texto, publicado_em e corrige o valor acentuado de categoria.

Nenhum registro é removido. A reversão desfaz os vínculos e apaga apenas as
linhas criadas por esta migration.
"""

import unicodedata

from django.db import migrations
from django.utils.text import slugify

# Congelado: ver comentário em 0006/0007.
REGIOES = [
    ("plano-piloto", "Plano Piloto"), ("asa-sul", "Asa Sul"), ("asa-norte", "Asa Norte"),
    ("lago-sul", "Lago Sul"), ("lago-norte", "Lago Norte"), ("sudoeste", "Sudoeste/Octogonal"),
    ("noroeste", "Noroeste"), ("cruzeiro", "Cruzeiro"), ("aguas-claras", "Águas Claras"),
    ("taguatinga", "Taguatinga"), ("ceilandia", "Ceilândia"), ("guara", "Guará"),
    ("samambaia", "Samambaia"), ("vicente-pires", "Vicente Pires"), ("sobradinho", "Sobradinho"),
    ("planaltina", "Planaltina"), ("gama", "Gama"), ("santa-maria", "Santa Maria"),
    ("recanto-das-emas", "Recanto das Emas"), ("riacho-fundo", "Riacho Fundo"),
    ("nucleo-bandeirante", "Núcleo Bandeirante"), ("park-way", "Park Way"),
    ("jardim-botanico", "Jardim Botânico"), ("sao-sebastiao", "São Sebastião"),
    ("paranoa", "Paranoá"), ("brazlandia", "Brazlândia"), ("entorno", "Entorno do DF"),
    ("online", "Online"),
]
ROTULO_REGIAO = dict(REGIOES)
ROTULO_CATEGORIA = {
    "shows": "Shows", "festas": "Festas", "musica": "Música", "festivais": "Festivais",
    "teatro": "Teatro", "cinema": "Cinema", "cultura": "Cultura", "gastronomia": "Gastronomia",
    "esportes": "Esportes", "tecnologia": "Tecnologia", "negocios": "Negócios",
    "networking": "Networking", "educacao": "Educação", "workshops": "Workshops",
    "cursos": "Cursos", "exposicoes": "Exposições", "arte": "Arte", "infantil": "Infantil",
    "familia": "Família", "religioso": "Religioso", "corporativo": "Corporativo",
    "universitario": "Universitário", "ar-livre": "Ar livre", "outros": "Outros",
}

# Sufixos que não distinguem um local de outro: "Cine Brasília - Asa Sul" e
# "Cine Brasília" são o mesmo cinema.
SUFIXOS_IGNORADOS = tuple(f" - {rotulo}" for _, rotulo in REGIOES) + (
    " - brasilia", " - brasília", " (brasilia)", " (brasília)", " - df", " / df",
)

MARCA_MIGRACAO = "migracao-0008"


def normalizar(texto):
    if not texto:
        return ""
    base = unicodedata.normalize("NFKD", str(texto))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return " ".join(base.lower().split())


def chave_local(nome):
    chave = normalizar(nome)
    mudou = True
    while mudou:
        mudou = False
        for sufixo in SUFIXOS_IGNORADOS:
            alvo = normalizar(sufixo)
            if alvo and chave.endswith(alvo):
                chave = chave[: -len(alvo)].strip(" -/(),")
                mudou = True
    return chave or normalizar(nome)


def slug_unico(usados, base_texto, prefixo, tamanho=200):
    base = slugify(base_texto)[:tamanho] or prefixo
    if base.isdigit():
        base = f"{prefixo}-{base}"
    slug, sufixo = base, 2
    while slug in usados:
        slug = f"{base}-{sufixo}"
        sufixo += 1
    usados.add(slug)
    return slug


def montar_busca(evento, organizador):
    partes = [
        evento.nome, evento.resumo, evento.descricao, evento.local, evento.endereco,
        organizador, evento.cidade,
        ROTULO_CATEGORIA.get(evento.categoria, ""),
        ROTULO_REGIAO.get(evento.regiao, ""),
    ]
    return normalizar(" ".join(p for p in partes if p))[:8000]


def migrar(apps, schema_editor):
    Evento = apps.get_model("eventos", "Evento")
    Local = apps.get_model("eventos", "Local")
    Produtor = apps.get_model("eventos", "Produtor")

    # 1. Categoria com acento no valor -> slug ASCII.
    Evento.objects.filter(categoria="universitário").update(categoria="universitario")

    locais_por_chave = {}
    produtores_por_chave = {}
    slugs_local, slugs_produtor = set(), set()

    for evento in Evento.objects.all().iterator():
        atualizar = []

        # 2. Local
        nome_local = (evento.local or "").strip()
        if nome_local and evento.local_ref_id is None:
            chave = chave_local(nome_local)
            local = locais_por_chave.get(chave)
            if local is None:
                local = Local.objects.filter(nome_normalizado=chave).first()
            if local is None:
                local = Local.objects.create(
                    nome=nome_local[:200],
                    slug=slug_unico(slugs_local, nome_local[:200], "local"),
                    nome_normalizado=chave[:200],
                    endereco=(evento.endereco or "")[:300],
                    regiao=evento.regiao or "",
                    cidade=evento.cidade or "Brasília",
                    descricao=MARCA_MIGRACAO,
                )
            else:
                # O primeiro evento cria o local; os seguintes completam buracos.
                mudou = []
                if not local.endereco and evento.endereco:
                    local.endereco = evento.endereco[:300]
                    mudou.append("endereco")
                if not local.regiao and evento.regiao:
                    local.regiao = evento.regiao
                    mudou.append("regiao")
                if mudou:
                    local.save(update_fields=mudou)
            locais_por_chave[chave] = local
            evento.local_ref_id = local.pk
            atualizar.append("local_ref")

        # 3. Produtor
        nome_produtor = (evento.organizador or "").strip()
        if nome_produtor and evento.produtor_id is None:
            chave = normalizar(nome_produtor)
            produtor = produtores_por_chave.get(chave)
            if produtor is None:
                produtor = Produtor.objects.filter(nome_normalizado=chave).first()
            if produtor is None:
                produtor = Produtor.objects.create(
                    nome=nome_produtor[:200],
                    slug=slug_unico(slugs_produtor, nome_produtor[:200], "produtor"),
                    nome_normalizado=chave[:200],
                    bio=MARCA_MIGRACAO,
                )
            produtores_por_chave[chave] = produtor
            evento.produtor_id = produtor.pk
            atualizar.append("produtor")

        # 4. Data de publicação, para quem já está publicado.
        if evento.status == "publicado" and evento.publicado_em is None:
            evento.publicado_em = evento.criado_em or evento.data
            atualizar.append("publicado_em")

        # 5. Coluna de busca.
        evento.busca_texto = montar_busca(evento, nome_produtor)
        atualizar.append("busca_texto")

        evento.save(update_fields=atualizar)

    # 6. Local do evento online não é um endereço físico.
    Local.objects.filter(descricao=MARCA_MIGRACAO, regiao="online").update(
        cidade="", geocodificacao_falhou=True
    )
    Local.objects.filter(descricao=MARCA_MIGRACAO).update(descricao="")
    Produtor.objects.filter(bio=MARCA_MIGRACAO).update(bio="")


def reverter(apps, schema_editor):
    Evento = apps.get_model("eventos", "Evento")
    Local = apps.get_model("eventos", "Local")
    Produtor = apps.get_model("eventos", "Produtor")

    Evento.objects.update(local_ref=None, produtor=None, busca_texto="", publicado_em=None)
    Evento.objects.filter(categoria="universitario").update(categoria="universitário")
    # Só some o que esta migration criou; qualquer local cadastrado depois fica.
    Local.objects.filter(eventos__isnull=True).delete()
    Produtor.objects.filter(eventos__isnull=True, user__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [("eventos", "0007_local_produtor_capacidade")]

    operations = [migrations.RunPython(migrar, reverter)]
