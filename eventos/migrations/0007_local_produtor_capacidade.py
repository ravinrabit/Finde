"""Local, Produtor, capacidade de evento, coluna de busca e registro de aceite.

As listas de choices estão escritas por extenso de propósito: uma migration é o
retrato do banco naquele momento e não deve mudar de comportamento porque
eventos/constants.py mudou depois.
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

CATEGORIAS = [
    ("shows", "Shows"), ("festas", "Festas"), ("musica", "Música"),
    ("festivais", "Festivais"), ("teatro", "Teatro"), ("cinema", "Cinema"),
    ("cultura", "Cultura"), ("gastronomia", "Gastronomia"), ("esportes", "Esportes"),
    ("tecnologia", "Tecnologia"), ("negocios", "Negócios"), ("networking", "Networking"),
    ("educacao", "Educação"), ("workshops", "Workshops"), ("cursos", "Cursos"),
    ("exposicoes", "Exposições"), ("arte", "Arte"), ("infantil", "Infantil"),
    ("familia", "Família"), ("religioso", "Religioso"), ("corporativo", "Corporativo"),
    ("universitario", "Universitário"), ("ar-livre", "Ar livre"), ("outros", "Outros"),
]

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


class Migration(migrations.Migration):

    dependencies = [
        ("eventos", "0006_modelo_eventos_v2"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # LOCAL
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Local",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200, verbose_name="nome")),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("nome_normalizado", models.CharField(db_index=True, editable=False, max_length=200)),
                ("endereco", models.CharField(blank=True, max_length=300, verbose_name="endereço")),
                ("referencia", models.CharField(blank=True, max_length=200, verbose_name="ponto de referência")),
                ("regiao", models.CharField(blank=True, choices=REGIOES, max_length=32, verbose_name="região")),
                ("cidade", models.CharField(default="Brasília", max_length=100)),
                ("cep", models.CharField(blank=True, max_length=9, verbose_name="CEP")),
                ("descricao", models.TextField(blank=True, verbose_name="descrição")),
                ("site", models.URLField(blank=True, max_length=600)),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ("geocodificado_em", models.DateTimeField(blank=True, editable=False, null=True)),
                ("geocodificacao_falhou", models.BooleanField(default=False, editable=False)),
                (
                    "coordenada_aproximada",
                    models.BooleanField(
                        default=False,
                        help_text="Marcado quando a coordenada veio do centro da região, não do endereço.",
                    ),
                ),
                (
                    "acessivel_cadeirante",
                    models.BooleanField(blank=True, null=True, verbose_name="acessível para cadeirante"),
                ),
                ("estacionamento", models.BooleanField(blank=True, null=True, verbose_name="tem estacionamento")),
                (
                    "metro_proximo",
                    models.CharField(blank=True, max_length=60, verbose_name="estação de metrô mais próxima"),
                ),
                ("metro_distancia_m", models.PositiveIntegerField(blank=True, editable=False, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "local",
                "verbose_name_plural": "locais",
                "ordering": ["nome"],
            },
        ),
        migrations.AddIndex(
            model_name="local",
            index=models.Index(fields=["regiao"], name="eventos_loc_regiao_idx"),
        ),
        migrations.AddIndex(
            model_name="local",
            index=models.Index(fields=["latitude", "longitude"], name="eventos_loc_geo_idx"),
        ),
        migrations.AddIndex(
            model_name="local",
            index=models.Index(fields=["nome_normalizado"], name="eventos_loc_nomenorm_idx"),
        ),

        # ------------------------------------------------------------------
        # PRODUTOR
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Produtor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200, verbose_name="nome")),
                ("slug", models.SlugField(blank=True, max_length=220, unique=True)),
                ("nome_normalizado", models.CharField(db_index=True, editable=False, max_length=200)),
                ("bio", models.TextField(blank=True, verbose_name="descrição")),
                ("logo", models.ImageField(blank=True, upload_to="produtores/%Y/%m/")),
                ("logo_url", models.URLField(blank=True, max_length=600)),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="e-mail de contato")),
                ("site", models.URLField(blank=True, max_length=600)),
                ("instagram", models.CharField(blank=True, help_text="Só o @, sem a URL.", max_length=100)),
                ("whatsapp", models.CharField(blank=True, max_length=30)),
                (
                    "verificado",
                    models.BooleanField(
                        default=False,
                        help_text="Produtor cuja identidade foi conferida pela equipe.",
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="produtor",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "produtor",
                "verbose_name_plural": "produtores",
                "ordering": ["nome"],
            },
        ),
        migrations.AddIndex(
            model_name="produtor",
            index=models.Index(fields=["verificado"], name="eventos_pro_verif_idx"),
        ),
        migrations.AddIndex(
            model_name="produtor",
            index=models.Index(fields=["nome_normalizado"], name="eventos_pro_nomenorm_idx"),
        ),

        # ------------------------------------------------------------------
        # INTEGRAÇÃO SYMPLA (token cedido pelo produtor)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="IntegracaoSympla",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=255)),
                ("ativa", models.BooleanField(default=True)),
                ("ultima_sincronizacao", models.DateTimeField(blank=True, null=True)),
                ("ultimo_erro", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                (
                    "produtor",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sympla",
                        to="eventos.produtor",
                    ),
                ),
            ],
            options={
                "verbose_name": "integração Sympla",
                "verbose_name_plural": "integrações Sympla",
            },
        ),

        # ------------------------------------------------------------------
        # ACEITE DE TERMOS (LGPD)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="AceiteDeTermos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("versao_termos", models.CharField(max_length=20)),
                ("versao_privacidade", models.CharField(max_length=20)),
                ("aceito_em", models.DateTimeField(auto_now_add=True)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="aceites",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "aceite de termos",
                "verbose_name_plural": "aceites de termos",
                "ordering": ["-aceito_em"],
            },
        ),

        # ------------------------------------------------------------------
        # EVENTO — novos campos
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="evento",
            name="local_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="eventos",
                to="eventos.local",
                verbose_name="local cadastrado",
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="produtor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="eventos",
                to="eventos.produtor",
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, editable=False, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, editable=False, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="capacidade",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Total de lugares. Em branco = sem limite de reservas.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="limite_por_usuario",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Máximo de ingressos que uma mesma pessoa pode reservar neste evento.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="motivo_rejeicao",
            field=models.TextField(
                blank=True,
                help_text="Mostrado ao produtor e enviado por e-mail quando o evento é rejeitado.",
            ),
        ),
        migrations.AddField(
            model_name="evento",
            name="publicado_em",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="evento",
            name="busca_texto",
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AlterField(
            model_name="evento",
            name="categoria",
            field=models.CharField(blank=True, choices=CATEGORIAS, max_length=32),
        ),
        migrations.AlterField(
            model_name="evento",
            name="regiao",
            field=models.CharField(blank=True, choices=REGIOES, max_length=32, verbose_name="região"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["latitude", "longitude"], name="eventos_eve_geo_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["local_ref", "data"], name="eventos_eve_localref_idx"),
        ),
        migrations.AddIndex(
            model_name="evento",
            index=models.Index(fields=["produtor", "data"], name="eventos_eve_produtor_idx"),
        ),
        migrations.AddConstraint(
            model_name="evento",
            constraint=models.CheckConstraint(
                condition=Q(capacidade__isnull=True) | Q(capacidade__gte=0),
                name="evento_capacidade_nao_negativa",
            ),
        ),

        # ------------------------------------------------------------------
        # INGRESSO
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="ingresso",
            name="utilizado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ingresso",
            name="cancelado_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="ingresso",
            index=models.Index(fields=["evento", "status"], name="eventos_ing_ev_status_idx"),
        ),
    ]
