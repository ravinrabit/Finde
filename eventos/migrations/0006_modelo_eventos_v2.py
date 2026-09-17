import re
from decimal import Decimal, InvalidOperation

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
from django.utils.text import slugify


# ---------------------------------------------------------------------------
# Estado congelado das listas na data desta migration.
#
# Antes, este arquivo importava eventos.constants. Uma migration é o retrato do
# banco naquele momento: se as constantes mudarem, uma migration antiga passa a
# se comportar de outro jeito numa instalação limpa. Foi exatamente o que
# aconteceria ao corrigir Categoria.UNIVERSITARIO ("universitário" ->
# "universitario"). As listas abaixo reproduzem o estado original.
# ---------------------------------------------------------------------------

CATEGORIAS_0006 = [
    ("shows", "Shows"), ("festas", "Festas"), ("musica", "Música"),
    ("festivais", "Festivais"), ("teatro", "Teatro"), ("cinema", "Cinema"),
    ("cultura", "Cultura"), ("gastronomia", "Gastronomia"), ("esportes", "Esportes"),
    ("tecnologia", "Tecnologia"), ("negocios", "Negócios"), ("networking", "Networking"),
    ("educacao", "Educação"), ("workshops", "Workshops"), ("cursos", "Cursos"),
    ("exposicoes", "Exposições"), ("arte", "Arte"), ("infantil", "Infantil"),
    ("familia", "Família"), ("religioso", "Religioso"), ("corporativo", "Corporativo"),
    ("universitário", "Universitário"), ("ar-livre", "Ar livre"), ("outros", "Outros"),
]

REGIOES_0006 = [
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


def _parse_preco(texto):
    if not texto:
        return None
    limpo = texto.strip().lower()
    if any(p in limpo for p in ("grátis", "gratis", "gratuito", "free")):
        return Decimal("0.00")
    numeros = re.findall(r"\d[\d.,]*", limpo)
    if not numeros:
        return None
    candidatos = []
    for bruto in numeros:
        normalizado = bruto.replace(".", "").replace(",", ".") if "," in bruto else bruto.replace(",", "")
        try:
            candidatos.append(Decimal(normalizado))
        except InvalidOperation:
            continue
    return min(candidatos) if candidatos else None


_ALIAS_CATEGORIA = {
    "show": "shows",
    "musica": "musica",
    "festa": "festas",
    "balada": "festas",
    "festival": "festivais",
    "teatro": "teatro",
    "cinema": "cinema",
    "cultura": "cultura",
    "gastronomia": "gastronomia",
    "comida": "gastronomia",
    "esporte": "esportes",
    "tecnologia": "tecnologia",
    "negocio": "negocios",
    "networking": "networking",
    "educacao": "educacao",
    "workshop": "workshops",
    "curso": "cursos",
    "exposicao": "exposicoes",
    "arte": "arte",
    "infantil": "infantil",
    "familia": "familia",
    "religioso": "religioso",
    "palestra": "educacao",
    "corporativo": "corporativo",
    "universitario": "universitário",
}

_VALORES_CATEGORIA = {v for v, _ in CATEGORIAS_0006}
_VALORES_REGIAO = {v for v, _ in REGIOES_0006}
_ROTULOS_REGIAO = sorted(
    ((slugify(rotulo), valor) for valor, rotulo in REGIOES_0006),
    key=lambda par: len(par[0]),
    reverse=True,
)


def _normalizar_categoria(bruto):
    if not bruto:
        return ""
    chave = slugify(bruto)
    if chave in _VALORES_CATEGORIA:
        return chave
    for alias, destino in _ALIAS_CATEGORIA.items():
        if alias in chave:
            return destino
    return "outros"


def _inferir_regiao(*textos):
    alvo = slugify(" ".join(t for t in textos if t))
    for rotulo, valor in _ROTULOS_REGIAO:
        if rotulo and rotulo in alvo:
            return valor
    return ""


def migrar_dados(apps, schema_editor):
    Evento = apps.get_model("eventos", "Evento")
    Ingresso = apps.get_model("eventos", "Ingresso")

    usados = set()
    for evento in Evento.objects.all().iterator():
        base = slugify(evento.nome)[:280] or "evento"
        slug = base
        sufixo = 2
        while slug in usados:
            slug = f"{base}-{sufixo}"
            sufixo += 1
        usados.add(slug)
        evento.slug = slug

        evento.preco = None if evento.gratuito else _parse_preco(evento.preco_legado)
        evento.categoria = _normalizar_categoria(evento.categoria)
        evento.regiao = _inferir_regiao(evento.local, evento.endereco)

        if evento.status == "aprovado":
            evento.status = "publicado"
        if not evento.ativo and evento.status == "publicado":
            evento.status = "arquivado"

        if evento.imagem is None:
            evento.imagem = ""
        if evento.data_fim and evento.data_fim < evento.data:
            evento.data_fim = None

        evento.save(
            update_fields=[
                "slug", "preco", "categoria", "regiao", "status", "imagem", "data_fim",
            ]
        )

    Ingresso.objects.filter(status="pendente").update(status="confirmado")


def reverter_dados(apps, schema_editor):
    Evento = apps.get_model("eventos", "Evento")
    for evento in Evento.objects.all().iterator():
        evento.preco_legado = "" if evento.preco is None else f"R$ {evento.preco:.2f}"
        evento.ativo = evento.status in ("publicado", "pendente")
        if evento.status == "publicado":
            evento.status = "aprovado"
        evento.save(update_fields=["preco_legado", "ativo", "status"])


class Migration(migrations.Migration):

    dependencies = [
        ("eventos", "0005_evento_imagem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- prepara colunas para receber os dados convertidos ---
        migrations.RenameField(model_name="evento", old_name="preco", new_name="preco_legado"),
        migrations.AddField(
            model_name="evento",
            name="preco",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="slug",
            field=models.SlugField(blank=True, default="", max_length=320),
        ),
        migrations.AddField(
            model_name="evento",
            name="regiao",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="evento",
            name="modalidade",
            field=models.CharField(default="presencial", max_length=12),
        ),
        migrations.AddField(
            model_name="evento",
            name="organizador",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="evento",
            name="resumo",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="evento",
            name="visualizacoes",
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name="evento",
            name="criado_em",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="atualizado_em",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="evento",
            name="status",
            field=models.CharField(default="publicado", max_length=12),
        ),
        migrations.AlterField(
            model_name="evento",
            name="imagem",
            field=models.ImageField(blank=True, null=True, upload_to="eventos/%Y/%m/"),
        ),

        migrations.RunPython(migrar_dados, reverter_dados),

        # --- descarta as colunas legadas e trava o schema definitivo ---
        migrations.RemoveField(model_name="evento", name="preco_legado"),
        migrations.RemoveField(model_name="evento", name="ativo"),
        migrations.AlterField(
            model_name="evento",
            name="slug",
            field=models.SlugField(blank=True, max_length=320, unique=True),
        ),
        migrations.AlterField(
            model_name="evento",
            name="imagem",
            field=models.ImageField(blank=True, upload_to="eventos/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="preco",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Deixe em branco se o valor ainda não foi definido.",
                max_digits=9,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="preço a partir de",
            ),
        ),
        migrations.AlterField(
            model_name="evento",
            name="categoria",
            field=models.CharField(blank=True, choices=CATEGORIAS_0006, max_length=32),
        ),
        migrations.AlterField(
            model_name="evento",
            name="regiao",
            field=models.CharField(
                blank=True, choices=REGIOES_0006, max_length=32, verbose_name="região"
            ),
        ),
        migrations.AlterField(
            model_name="evento",
            name="modalidade",
            field=models.CharField(
                choices=[
                    ("presencial", "Presencial"),
                    ("online", "Online"),
                    ("hibrido", "Híbrido"),
                ],
                default="presencial",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="evento",
            name="status",
            field=models.CharField(
                choices=[
                    ("pendente", "Aguardando aprovação"),
                    ("publicado", "Publicado"),
                    ("rejeitado", "Rejeitado"),
                    ("arquivado", "Arquivado"),
                ],
                default="publicado",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="evento",
            name="fonte",
            field=models.CharField(default="manual", max_length=50),
        ),
        migrations.AlterField(
            model_name="evento",
            name="id_externo",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="evento",
            name="imagem_url",
            field=models.URLField(blank=True, max_length=600),
        ),
        migrations.AlterField(
            model_name="evento",
            name="link_original",
            field=models.URLField(blank=True, max_length=600),
        ),
        migrations.AlterField(
            model_name="evento",
            name="link_ingressos",
            field=models.URLField(blank=True, max_length=600),
        ),
        migrations.AlterField(
            model_name="evento",
            name="criado_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="eventos_criados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="evento",
            name="descricao",
            field=models.TextField(blank=True, verbose_name="descrição"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="nome",
            field=models.CharField(max_length=300, verbose_name="nome"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="data",
            field=models.DateTimeField(verbose_name="início"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="data_fim",
            field=models.DateTimeField(blank=True, null=True, verbose_name="término"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="local",
            field=models.CharField(max_length=300, verbose_name="local"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="endereco",
            field=models.CharField(blank=True, max_length=300, verbose_name="endereço"),
        ),
        migrations.AlterField(
            model_name="evento",
            name="gratuito",
            field=models.BooleanField(default=False, verbose_name="gratuito"),
        ),
        migrations.AlterModelOptions(
            name="evento",
            options={
                "ordering": ["data"],
                "verbose_name": "evento",
                "verbose_name_plural": "eventos",
            },
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["status", "data"], name="eventos_eve_status_data_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["categoria", "data"], name="eventos_eve_categ_data_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["regiao", "data"], name="eventos_eve_regia_data_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["gratuito", "data"], name="eventos_eve_grati_data_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["destaque", "data"], name="eventos_eve_desta_data_idx"),
        ),
        migrations.AddConstraint(
            model_name="evento",
            constraint=models.CheckConstraint(
                condition=Q(data_fim__isnull=True) | Q(data_fim__gte=F("data")),
                name="evento_data_fim_apos_inicio",
            ),
        ),
        migrations.AddConstraint(
            model_name="evento",
            constraint=models.UniqueConstraint(
                condition=~Q(id_externo=""),
                fields=("fonte", "id_externo"),
                name="evento_unico_por_fonte",
            ),
        ),

        # --- ingressos ---
        migrations.AlterField(
            model_name="ingresso",
            name="status",
            field=models.CharField(
                choices=[
                    ("confirmado", "Confirmado"),
                    ("cancelado", "Cancelado"),
                    ("utilizado", "Utilizado"),
                ],
                default="confirmado",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="ingresso",
            name="valor",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=9),
        ),
        migrations.AlterModelOptions(
            name="ingresso",
            options={
                "ordering": ["-data_compra"],
                "verbose_name": "ingresso",
                "verbose_name_plural": "ingressos",
            },
        ),
        migrations.AddIndex(
            model_name="ingresso",
            index=models.Index(fields=["usuario", "status"], name="eventos_ing_user_status_idx"),
        ),

        # --- favoritos ---
        migrations.CreateModel(
            name="Favorito",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "evento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favoritado_por",
                        to="eventos.evento",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="favoritos",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "favorito",
                "verbose_name_plural": "favoritos",
                "ordering": ["-criado_em"],
            },
        ),
        migrations.AddConstraint(
            model_name="favorito",
            constraint=models.UniqueConstraint(
                fields=("usuario", "evento"), name="favorito_unico"
            ),
        ),
    ]
