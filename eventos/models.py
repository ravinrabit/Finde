import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .constants import (
    CENTROIDE_POR_REGIAO,
    ESTACOES_METRO_DF,
    Categoria,
    Modalidade,
    Regiao,
    normalizar,
)

RAIO_TERRA_KM = 6371.0088

# Nomes que ocupam o campo "local" sem designar um lugar. Não viram Local:
# um marcador chamado "A confirmar" no mapa é pior do que marcador nenhum.
LOCAIS_SEM_ENDERECO = {
    "a confirmar", "a definir", "a ser definido", "local a confirmar",
    "local a definir", "online", "internet", "transmissao online", "remoto",
}


def formatar_reais(valor):
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {milhar},{centavos}"


def distancia_km(lat1, lon1, lat2, lon2):
    """Haversine. Suficiente para o DF, onde os erros ficam abaixo de 1 m."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(math.sqrt(a))


def gerar_slug(modelo, base_texto, pk=None, tamanho=280, prefixo="item"):
    """Slug único, com sufixo numérico em caso de colisão.

    A checagem aqui não elimina a corrida entre dois salvamentos simultâneos —
    quem garante a unicidade é a constraint do banco. Por isso os save() que
    usam isto tratam IntegrityError e tentam de novo.
    """
    base = slugify(base_texto)[:tamanho] or prefixo
    if base.isdigit():
        base = f"{prefixo}-{base}"
    slug, sufixo = base, 2
    while modelo.objects.filter(slug=slug).exclude(pk=pk).exists():
        slug = f"{base}-{sufixo}"
        sufixo += 1
    return slug


# =========================
# LOCAL
# =========================

class LocalQuerySet(models.QuerySet):
    def com_coordenadas(self):
        return self.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    def pendentes_de_geocodificacao(self):
        return self.filter(latitude__isnull=True, geocodificacao_falhou=False).exclude(
            regiao=Regiao.ONLINE
        )


class Local(models.Model):
    """Um espaço físico do DF. Um local, muitos eventos.

    O campo Evento.local (texto) continua existindo e é mantido em sincronia:
    tudo que já lia evento.local continua funcionando enquanto as páginas
    passam a usar evento.local_ref.
    """

    nome = models.CharField("nome", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    # Chave de deduplicação: "Cine Brasília" e "Cine Brasilia" colidem aqui.
    nome_normalizado = models.CharField(max_length=200, editable=False, db_index=True)

    endereco = models.CharField("endereço", max_length=300, blank=True)
    referencia = models.CharField("ponto de referência", max_length=200, blank=True)
    regiao = models.CharField("região", max_length=32, choices=Regiao.choices, blank=True)
    cidade = models.CharField(max_length=100, default="Brasília")
    cep = models.CharField("CEP", max_length=9, blank=True)
    descricao = models.TextField("descrição", blank=True)
    site = models.URLField(max_length=600, blank=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geocodificado_em = models.DateTimeField(null=True, blank=True, editable=False)
    geocodificacao_falhou = models.BooleanField(default=False, editable=False)
    coordenada_aproximada = models.BooleanField(
        default=False,
        help_text="Marcado quando a coordenada veio do centro da região, não do endereço.",
    )

    acessivel_cadeirante = models.BooleanField("acessível para cadeirante", null=True, blank=True)
    estacionamento = models.BooleanField("tem estacionamento", null=True, blank=True)
    metro_proximo = models.CharField("estação de metrô mais próxima", max_length=60, blank=True)
    metro_distancia_m = models.PositiveIntegerField(null=True, blank=True, editable=False)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = LocalQuerySet.as_manager()

    class Meta:
        verbose_name = "local"
        verbose_name_plural = "locais"
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["regiao"], name="eventos_loc_regiao_idx"),
            models.Index(fields=["latitude", "longitude"], name="eventos_loc_geo_idx"),
            models.Index(fields=["nome_normalizado"], name="eventos_loc_nomenorm_idx"),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome_normalizado = normalizar(self.nome)
        if not self.slug:
            self.slug = gerar_slug(Local, self.nome, self.pk, tamanho=200, prefixo="local")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("local_detalhe", args=[self.slug])

    @property
    def tem_coordenadas(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def endereco_completo(self):
        partes = [self.endereco, self.get_regiao_display() if self.regiao else "", self.cidade]
        return ", ".join(p for p in partes if p)

    def coordenadas_ou_centroide(self):
        if self.tem_coordenadas:
            return float(self.latitude), float(self.longitude)
        return CENTROIDE_POR_REGIAO.get(self.regiao)

    def atualizar_metro(self, raio_m=None):
        """Guarda a estação mais próxima. Só faz sentido com coordenada real."""
        from django.conf import settings as _s

        raio_m = raio_m or getattr(_s, "METRO_RAIO_PADRAO_M", 1000)
        if not self.tem_coordenadas:
            self.metro_proximo, self.metro_distancia_m = "", None
            return False
        melhor, menor = None, None
        for nome, lat, lon in ESTACOES_METRO_DF:
            d = distancia_km(self.latitude, self.longitude, lat, lon)
            if d is not None and (menor is None or d < menor):
                melhor, menor = nome, d
        if melhor is None or menor * 1000 > raio_m * 5:
            self.metro_proximo, self.metro_distancia_m = "", None
            return False
        self.metro_proximo = melhor
        self.metro_distancia_m = int(round(menor * 1000))
        return True


# =========================
# PRODUTOR
# =========================

class Produtor(models.Model):
    """Quem organiza. Antes era só um CharField em Evento."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="produtor",
    )
    nome = models.CharField("nome", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    nome_normalizado = models.CharField(max_length=200, editable=False, db_index=True)

    bio = models.TextField("descrição", blank=True)
    logo = models.ImageField(upload_to="produtores/%Y/%m/", blank=True)
    logo_url = models.URLField(max_length=600, blank=True)
    email = models.EmailField("e-mail de contato", blank=True)
    site = models.URLField(max_length=600, blank=True)
    instagram = models.CharField(max_length=100, blank=True, help_text="Só o @, sem a URL.")
    whatsapp = models.CharField(max_length=30, blank=True)

    verificado = models.BooleanField(
        default=False,
        help_text="Produtor cuja identidade foi conferida pela equipe.",
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "produtor"
        verbose_name_plural = "produtores"
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["verificado"], name="eventos_pro_verif_idx"),
            models.Index(fields=["nome_normalizado"], name="eventos_pro_nomenorm_idx"),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome_normalizado = normalizar(self.nome)
        if not self.slug:
            self.slug = gerar_slug(Produtor, self.nome, self.pk, tamanho=200, prefixo="produtor")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("produtor_detalhe", args=[self.slug])

    @property
    def logo_exibicao(self):
        if self.logo:
            return self.logo.url
        return self.logo_url

    @property
    def instagram_url(self):
        if not self.instagram:
            return ""
        return f"https://instagram.com/{self.instagram.lstrip('@')}"


class IntegracaoSympla(models.Model):
    """Token de API da Sympla cedido pelo próprio produtor.

    A API pública da Sympla só devolve os eventos do dono do token, então esta
    é a única forma legítima de importar de lá: o produtor autoriza.

    ATENÇÃO: o token é credencial de terceiro. Ele nunca aparece em listagem,
    nunca é devolvido em exportação LGPD e o campo é write-only no admin.
    Em produção, use criptografia em repouso no banco (pgcrypto ou disco
    criptografado). Ver README, seção "Integrações".
    """

    produtor = models.OneToOneField(Produtor, on_delete=models.CASCADE, related_name="sympla")
    token = models.CharField(max_length=255)
    ativa = models.BooleanField(default=True)
    ultima_sincronizacao = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "integração Sympla"
        verbose_name_plural = "integrações Sympla"

    def __str__(self):
        return f"Sympla — {self.produtor.nome}"


# =========================
# EVENTO
# =========================

class EventoQuerySet(models.QuerySet):
    def publicados(self):
        return self.filter(status=Evento.Status.PUBLICADO)

    def futuros(self):
        agora = timezone.now()
        return self.filter(
            Q(data_fim__gte=agora) | Q(data_fim__isnull=True, data__gte=agora)
        )

    def visiveis(self):
        return self.publicados().futuros()

    def com_capa(self):
        return self.exclude(imagem="", imagem_url="")

    def entre(self, inicio, fim):
        return self.filter(data__lte=fim).filter(
            Q(data_fim__gte=inicio) | Q(data_fim__isnull=True, data__gte=inicio)
        )

    def com_coordenadas(self):
        return self.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    def para_cards(self):
        """select_related do que todo card renderiza. Evita N+1 nas listagens."""
        return self.select_related("local_ref", "produtor")

    def no_raio(self, lat, lon, raio_km):
        """Recorte retangular por bounding box, depois filtro exato em Python.

        A caixa é feita no banco (usa índice) e serve para não trazer a tabela
        inteira; o círculo de verdade é aplicado em `ordenar_por_distancia`.
        """
        graus_lat = raio_km / 110.574
        graus_lon = raio_km / (111.320 * max(math.cos(math.radians(lat)), 0.01))
        return self.com_coordenadas().filter(
            latitude__gte=lat - graus_lat,
            latitude__lte=lat + graus_lat,
            longitude__gte=lon - graus_lon,
            longitude__lte=lon + graus_lon,
        )


class Evento(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Aguardando aprovação"
        PUBLICADO = "publicado", "Publicado"
        REJEITADO = "rejeitado", "Rejeitado"
        ARQUIVADO = "arquivado", "Arquivado"

    # Campos cuja alteração devolve um evento publicado para a fila de revisão.
    CAMPOS_SENSIVEIS = (
        "nome", "data", "data_fim", "local", "endereco", "regiao", "cidade",
        "modalidade", "preco", "gratuito", "link_ingressos", "organizador",
    )

    nome = models.CharField("nome", max_length=300)
    slug = models.SlugField(max_length=320, unique=True, blank=True)
    descricao = models.TextField("descrição", blank=True)
    resumo = models.CharField("resumo", max_length=200, blank=True)

    data = models.DateTimeField("início")
    data_fim = models.DateTimeField("término", null=True, blank=True)

    modalidade = models.CharField(
        max_length=12, choices=Modalidade.choices, default=Modalidade.PRESENCIAL
    )
    # Nome do local como texto. Continua sendo a fonte de exibição, e é mantido
    # em sincronia com local_ref.nome no save().
    local = models.CharField("local", max_length=300)
    local_ref = models.ForeignKey(
        Local, null=True, blank=True, on_delete=models.SET_NULL, related_name="eventos",
        verbose_name="local cadastrado",
    )
    endereco = models.CharField("endereço", max_length=300, blank=True)
    regiao = models.CharField("região", max_length=32, choices=Regiao.choices, blank=True)
    cidade = models.CharField(max_length=100, default="Brasília")

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, editable=False)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, editable=False)

    categoria = models.CharField(max_length=32, choices=Categoria.choices, blank=True)

    gratuito = models.BooleanField("gratuito", default=False)
    preco = models.DecimalField(
        "preço a partir de",
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Deixe em branco se o valor ainda não foi definido.",
    )

    capacidade = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Total de lugares. Em branco = sem limite de reservas.",
    )
    limite_por_usuario = models.PositiveSmallIntegerField(
        default=10,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Máximo de ingressos que uma mesma pessoa pode reservar neste evento.",
    )

    organizador = models.CharField(max_length=200, blank=True)
    produtor = models.ForeignKey(
        Produtor, null=True, blank=True, on_delete=models.SET_NULL, related_name="eventos"
    )
    link_original = models.URLField(max_length=600, blank=True)
    link_ingressos = models.URLField(max_length=600, blank=True)

    imagem_url = models.URLField(max_length=600, blank=True)
    imagem = models.ImageField(upload_to="eventos/%Y/%m/", blank=True)

    fonte = models.CharField(max_length=50, default="manual")
    id_externo = models.CharField(max_length=120, blank=True)

    destaque = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PUBLICADO)
    motivo_rejeicao = models.TextField(
        blank=True, help_text="Mostrado ao produtor e enviado por e-mail quando o evento é rejeitado."
    )
    publicado_em = models.DateTimeField(null=True, blank=True, editable=False)
    visualizacoes = models.PositiveIntegerField(default=0, editable=False)

    # Texto único, minúsculo e sem acento, alimentado no save(). É o que a busca
    # consulta — resolve "cinéma"/"cinema" e "Brasília"/"brasilia" em SQLite e
    # em PostgreSQL, com uma coluna indexável em vez de cinco LIKE.
    busca_texto = models.TextField(editable=False, blank=True)

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="eventos_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True, null=True)

    objects = EventoQuerySet.as_manager()

    class Meta:
        verbose_name = "evento"
        verbose_name_plural = "eventos"
        ordering = ["data"]
        indexes = [
            models.Index(fields=["status", "data"], name="eventos_eve_status_data_idx"),
            models.Index(fields=["categoria", "data"], name="eventos_eve_categ_data_idx"),
            models.Index(fields=["regiao", "data"], name="eventos_eve_regia_data_idx"),
            models.Index(fields=["gratuito", "data"], name="eventos_eve_grati_data_idx"),
            models.Index(fields=["destaque", "data"], name="eventos_eve_desta_data_idx"),
            models.Index(fields=["latitude", "longitude"], name="eventos_eve_geo_idx"),
            models.Index(fields=["local_ref", "data"], name="eventos_eve_localref_idx"),
            models.Index(fields=["produtor", "data"], name="eventos_eve_produtor_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(data_fim__isnull=True) | Q(data_fim__gte=F("data")),
                name="evento_data_fim_apos_inicio",
            ),
            models.UniqueConstraint(
                fields=["fonte", "id_externo"],
                condition=~Q(id_externo=""),
                name="evento_unico_por_fonte",
            ),
            models.CheckConstraint(
                condition=Q(capacidade__isnull=True) | Q(capacidade__gte=0),
                name="evento_capacidade_nao_negativa",
            ),
        ]

    def __str__(self):
        return self.nome

    # -- persistência ----------------------------------------------------

    def save(self, *args, **kwargs):
        """Calcula os campos derivados e garante que eles cheguem ao banco.

        `update_fields` é uma armadilha aqui. Desde o Django 4.2,
        `update_or_create()` chama `save(update_fields=...)` com apenas as
        chaves de `defaults`. Um campo que este save() deriva — coordenada
        herdada do local, região inferida, busca_texto — era calculado em
        memória e depois **silenciosamente descartado** na escrita, porque não
        estava na lista.

        O efeito prático: um evento reimportado nunca recebia a coordenada do
        local nem a região inferida. Por isso cada derivação declara o que
        mexeu, e o conjunto é somado a `update_fields` no fim.
        """
        derivados = set()

        if self.gratuito and self.preco is not None:
            self.preco = None
            derivados.add("preco")

        if self.local_ref_id and not self.local:
            self.local = self.local_ref.nome
            derivados.add("local")

        if self._garantir_local():
            derivados.add("local_ref")

        derivados |= self._herdar_do_local()

        if self.status == self.Status.PUBLICADO and self.publicado_em is None:
            self.publicado_em = timezone.now()
            derivados.add("publicado_em")

        # Recalculado sempre: uma coluna de busca desatualizada é pior do que
        # não ter coluna de busca.
        self.busca_texto = self._montar_busca()
        derivados.add("busca_texto")

        if not self.slug:
            self.slug = gerar_slug(Evento, self.nome, self.pk, tamanho=280, prefixo="evento")
            derivados.add("slug")

        campos = kwargs.get("update_fields")
        if campos is not None:
            kwargs["update_fields"] = set(campos) | derivados

        super().save(*args, **kwargs)

    def _garantir_local(self):
        """Todo evento presencial com nome de local aponta para um Local.

        Antes disto, só a ingestão e o formulário do produtor criavam Local.
        Evento nascido do admin, de um script, do shell ou do semear_demo
        ficava com o nome do lugar em texto e `local_ref` vazio — e como o
        mapa e o filtro "perto de mim" dependem da coordenada, que vem do
        Local, esses eventos eram simplesmente invisíveis ali. O sintoma era
        um /mapa/ vazio mesmo com o catálogo cheio.

        O save() é o único ponto por onde toda criação passa, então é aqui que
        a garantia tem que morar. Devolve True quando vinculou.
        """
        if self.local_ref_id or self.modalidade == Modalidade.ONLINE:
            return False

        nome = (self.local or "").strip()
        chave = normalizar(nome)[:200]
        if not chave or chave in LOCAIS_SEM_ENDERECO:
            return False

        local = Local.objects.filter(nome_normalizado=chave).first()
        if local is None:
            local = Local.objects.create(
                nome=nome[:200],
                endereco=(self.endereco or "")[:300],
                regiao=self.regiao or "",
                cidade=self.cidade or "Brasília",
            )
        self.local_ref = local
        return True

    def _herdar_do_local(self):
        """Copia do local o que o evento precisa ter em coluna própria.

        As coordenadas ficam desnormalizadas no evento para o filtro por raio
        não precisar de JOIN em toda listagem.

        Devolve o conjunto de campos que realmente mudou, para que save()
        consiga incluí-los em update_fields.
        """
        mudou = set()

        if self.local_ref_id:
            local = self.local_ref
            if self.latitude != local.latitude or self.longitude != local.longitude:
                self.latitude = local.latitude
                self.longitude = local.longitude
                mudou |= {"latitude", "longitude"}
            if not self.regiao and local.regiao:
                self.regiao = local.regiao
                mudou.add("regiao")
            if not self.endereco and local.endereco:
                self.endereco = local.endereco
                mudou.add("endereco")
        elif self.modalidade == Modalidade.ONLINE:
            if self.latitude is not None or self.longitude is not None:
                self.latitude = self.longitude = None
                mudou |= {"latitude", "longitude"}

        return mudou

    def _montar_busca(self):
        organizador = self.produtor.nome if self.produtor_id else self.organizador
        partes = [
            self.nome, self.resumo, self.descricao, self.local,
            self.endereco, organizador, self.cidade,
            self.get_categoria_display() if self.categoria else "",
            self.get_regiao_display() if self.regiao else "",
        ]
        return normalizar(" ".join(p for p in partes if p))[:8000]

    def get_absolute_url(self):
        return reverse("evento_detalhe", args=[self.slug])

    # -- moderação -------------------------------------------------------

    @staticmethod
    def _comparavel(valor):
        """Normaliza um valor para comparação entre formulário e banco.

        O widget de data é <input type="datetime-local">, que tem precisão de
        MINUTO. O banco guarda o que veio da importação, que costuma ter
        segundos. Comparar os dois crus faz "20:00:37" e "20:00:00" parecerem
        datas diferentes — e aí toda edição de um evento importado seria lida
        como mudança de data.
        """
        if isinstance(valor, datetime):
            return valor.replace(second=0, microsecond=0)
        return valor

    def alteracoes_sensiveis(self, original):
        """Quais campos que exigem nova revisão mudaram em relação ao original."""
        if original is None:
            return []
        mudou = []
        for campo in self.CAMPOS_SENSIVEIS:
            atual = self._comparavel(getattr(self, campo, None))
            anterior = self._comparavel(getattr(original, campo, None))
            if atual != anterior:
                mudou.append(campo)
        if self.local_ref_id != original.local_ref_id:
            mudou.append("local_ref")
        return mudou

    # -- apresentação ----------------------------------------------------

    @property
    def imagem_exibicao(self):
        if self.imagem:
            return self.imagem.url
        return self.imagem_url

    @property
    def termino(self):
        return self.data_fim or self.data

    @property
    def ja_aconteceu(self):
        return self.termino < timezone.now()

    @property
    def acontecendo_agora(self):
        return self.data <= timezone.now() <= self.termino

    @property
    def dias_ate_comecar(self):
        return (timezone.localtime(self.data).date() - timezone.localdate()).days

    @property
    def e_hoje(self):
        return self.dias_ate_comecar == 0

    @property
    def preco_rotulo(self):
        if self.gratuito or self.preco == 0:
            return "Gratuito"
        if self.preco is None:
            return "Valor a definir"
        return f"A partir de {formatar_reais(self.preco)}"

    @property
    def organizador_nome(self):
        return self.produtor.nome if self.produtor_id else self.organizador

    @property
    def tem_coordenadas(self):
        return self.latitude is not None and self.longitude is not None

    # -- capacidade ------------------------------------------------------

    @property
    def ingressos_confirmados(self):
        return self.ingressos.exclude(status=Ingresso.Status.CANCELADO).count()

    @property
    def vagas_disponiveis(self):
        if self.capacidade is None:
            return None
        return max(0, self.capacidade - self.ingressos_confirmados)

    @property
    def esgotado(self):
        vagas = self.vagas_disponiveis
        return vagas is not None and vagas == 0

    @property
    def aceita_reserva(self):
        return (
            self.status == self.Status.PUBLICADO
            and not self.ja_aconteceu
            and not self.esgotado
        )

    def valor_para(self, tipo):
        if self.gratuito or self.preco is None:
            return Decimal("0.00")
        if tipo == Ingresso.Tipo.MEIA:
            return (self.preco / 2).quantize(Decimal("0.01"))
        return self.preco

    def registrar_visualizacao(self):
        Evento.objects.filter(pk=self.pk).update(visualizacoes=F("visualizacoes") + 1)

    def distancia_de(self, lat, lon):
        if not self.tem_coordenadas:
            return None
        return distancia_km(self.latitude, self.longitude, lat, lon)

    @staticmethod
    def janela_fim_de_semana():
        """Sexta 18h → domingo 23h59 da próxima ocorrência (ou da atual, se já começou)."""
        agora = timezone.localtime()
        if agora.weekday() in (4, 5, 6):
            sexta = agora - timedelta(days=agora.weekday() - 4)
        else:
            sexta = agora + timedelta(days=(4 - agora.weekday()) % 7)
        sexta = sexta.replace(hour=18, minute=0, second=0, microsecond=0)
        domingo = (sexta + timedelta(days=2)).replace(hour=23, minute=59, second=59)
        return max(sexta, agora), domingo


# =========================
# INGRESSOS
# =========================

class Ingresso(models.Model):
    class Tipo(models.TextChoices):
        INTEIRA = "inteira", "Inteira"
        MEIA = "meia", "Meia-entrada"

    class Status(models.TextChoices):
        CONFIRMADO = "confirmado", "Confirmado"
        CANCELADO = "cancelado", "Cancelado"
        UTILIZADO = "utilizado", "Utilizado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ingressos"
    )
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="ingressos")
    codigo = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.INTEIRA)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMADO)
    valor = models.DecimalField(max_digits=9, decimal_places=2, default=0)
    data_compra = models.DateTimeField(auto_now_add=True)
    utilizado_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "ingresso"
        verbose_name_plural = "ingressos"
        ordering = ["-data_compra"]
        indexes = [
            models.Index(fields=["usuario", "status"], name="eventos_ing_user_status_idx"),
            models.Index(fields=["evento", "status"], name="eventos_ing_ev_status_idx"),
        ]

    def __str__(self):
        return f"{self.evento.nome} — {self.usuario}"

    @property
    def codigo_curto(self):
        return str(self.codigo).split("-")[0].upper()

    @property
    def pode_cancelar(self):
        return self.status == self.Status.CONFIRMADO and not self.evento.ja_aconteceu

    @property
    def valor_rotulo(self):
        return "Gratuito" if self.valor == 0 else formatar_reais(self.valor)


# =========================
# FAVORITOS
# =========================

class Favorito(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favoritos"
    )
    evento = models.ForeignKey(Evento, on_delete=models.CASCADE, related_name="favoritado_por")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "favorito"
        verbose_name_plural = "favoritos"
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "evento"], name="favorito_unico")
        ]

    def __str__(self):
        return f"{self.usuario} — {self.evento}"


# =========================
# LGPD
# =========================

class AceiteDeTermos(models.Model):
    """Registro de consentimento: quem aceitou, qual versão e quando.

    A política de privacidade afirma que o consentimento é registrado. Antes
    disso existir, o aceite era só um checkbox que nada persistia.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="aceites"
    )
    versao_termos = models.CharField(max_length=20)
    versao_privacidade = models.CharField(max_length=20)
    aceito_em = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "aceite de termos"
        verbose_name_plural = "aceites de termos"
        ordering = ["-aceito_em"]

    def __str__(self):
        return f"{self.usuario} — termos {self.versao_termos}"
