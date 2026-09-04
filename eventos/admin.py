from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from . import emails
from .models import (
    AceiteDeTermos,
    Evento,
    Favorito,
    Ingresso,
    IntegracaoSympla,
    Local,
    Produtor,
)


# =========================
# LOCAL
# =========================

@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("nome", "regiao", "situacao_geo", "metro_proximo", "total_eventos", "acessivel_cadeirante")
    list_filter = ("regiao", "coordenada_aproximada", "acessivel_cadeirante", "estacionamento")
    search_fields = ("nome", "endereco", "nome_normalizado")
    prepopulated_fields = {"slug": ("nome",)}
    readonly_fields = ("nome_normalizado", "geocodificado_em", "metro_distancia_m", "criado_em", "atualizado_em")
    list_per_page = 50
    actions = ("recolocar_na_fila_de_geocodificacao", "recalcular_metro")

    fieldsets = (
        ("Identificação", {"fields": ("nome", "slug", "nome_normalizado", "descricao", "site")}),
        ("Endereço", {"fields": ("endereco", "referencia", "regiao", "cidade", "cep")}),
        (
            "Coordenadas",
            {
                "fields": ("latitude", "longitude", "coordenada_aproximada", "geocodificado_em"),
                "description": (
                    "Coordenada aproximada é o centro da região administrativa, usado quando "
                    "a geocodificação do endereço não resolve. Corrija aqui quando souber o ponto exato."
                ),
            },
        ),
        ("Acessibilidade e transporte", {"fields": ("acessivel_cadeirante", "estacionamento", "metro_proximo", "metro_distancia_m")}),
        ("Controle", {"fields": ("criado_em", "atualizado_em")}),
    )

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).annotate(_eventos=Count("eventos"))

    @admin.display(description="Eventos", ordering="_eventos")
    def total_eventos(self, obj):
        return obj._eventos

    @admin.display(description="Coordenada")
    def situacao_geo(self, obj):
        if not obj.tem_coordenadas:
            return format_html('<span style="color:#b91c1c">sem coordenada</span>')
        if obj.coordenada_aproximada:
            return format_html('<span style="color:#b45309">aproximada</span>')
        return format_html('<span style="color:#15803d">exata</span>')

    @admin.action(description="Geocodificar de novo na próxima execução")
    def recolocar_na_fila_de_geocodificacao(self, request, queryset):
        total = queryset.update(
            latitude=None, longitude=None, geocodificacao_falhou=False, coordenada_aproximada=False
        )
        self.message_user(
            request,
            f"{total} local(is) na fila. Rode: python manage.py geocodificar",
            messages.INFO,
        )

    @admin.action(description="Recalcular estação de metrô mais próxima")
    def recalcular_metro(self, request, queryset):
        total = 0
        for local in queryset:
            if local.atualizar_metro():
                local.save(update_fields=["metro_proximo", "metro_distancia_m"])
                total += 1
        self.message_user(request, f"{total} local(is) atualizado(s).")


# =========================
# PRODUTOR
# =========================

class IntegracaoSymplaInline(admin.StackedInline):
    model = IntegracaoSympla
    extra = 0
    fields = ("token", "ativa", "ultima_sincronizacao", "ultimo_erro")
    readonly_fields = ("ultima_sincronizacao", "ultimo_erro")


@admin.register(Produtor)
class ProdutorAdmin(admin.ModelAdmin):
    list_display = ("nome", "verificado", "user", "email", "total_eventos")
    list_filter = ("verificado",)
    search_fields = ("nome", "email", "nome_normalizado", "user__email")
    prepopulated_fields = {"slug": ("nome",)}
    autocomplete_fields = ("user",)
    readonly_fields = ("nome_normalizado", "criado_em", "atualizado_em")
    inlines = (IntegracaoSymplaInline,)
    actions = ("verificar", "remover_verificacao")
    list_per_page = 50

    def get_queryset(self, request):
        from django.db.models import Count

        return super().get_queryset(request).select_related("user").annotate(_eventos=Count("eventos"))

    @admin.display(description="Eventos", ordering="_eventos")
    def total_eventos(self, obj):
        return obj._eventos

    @admin.action(description="Marcar como verificado")
    def verificar(self, request, queryset):
        total = queryset.update(verificado=True)
        self.message_user(request, f"{total} produtor(es) verificado(s).")

    @admin.action(description="Remover verificação")
    def remover_verificacao(self, request, queryset):
        total = queryset.update(verificado=False)
        self.message_user(request, f"{total} produtor(es) sem verificação.")


@admin.register(IntegracaoSympla)
class IntegracaoSymplaAdmin(admin.ModelAdmin):
    """O token é credencial de terceiro: nunca aparece na listagem nem em leitura."""

    list_display = ("produtor", "ativa", "ultima_sincronizacao", "tem_erro")
    list_filter = ("ativa",)
    search_fields = ("produtor__nome",)
    autocomplete_fields = ("produtor",)
    readonly_fields = ("ultima_sincronizacao", "ultimo_erro", "criado_em")

    @admin.display(description="Erro", boolean=True)
    def tem_erro(self, obj):
        return bool(obj.ultimo_erro)


# =========================
# EVENTO
# =========================

@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "data", "local", "regiao", "categoria", "status",
        "ocupacao", "destaque", "fonte",
    )
    list_filter = ("status", "categoria", "regiao", "modalidade", "gratuito", "destaque", "fonte")
    search_fields = ("nome", "local", "organizador", "criado_por__email", "produtor__nome")
    date_hierarchy = "data"
    ordering = ("-data",)
    prepopulated_fields = {"slug": ("nome",)}
    autocomplete_fields = ("criado_por", "local_ref", "produtor")
    list_select_related = ("criado_por", "local_ref", "produtor")
    readonly_fields = (
        "visualizacoes", "publicado_em", "criado_em", "atualizado_em",
        "previa_imagem", "coordenadas", "ocupacao",
    )
    list_per_page = 40
    actions = ("publicar", "rejeitar", "arquivar", "marcar_destaque", "remover_destaque")

    fieldsets = (
        ("Identificação", {"fields": ("nome", "slug", "categoria", "destaque")}),
        (
            "Moderação",
            {
                "fields": ("status", "motivo_rejeicao", "publicado_em"),
                "description": (
                    "O motivo da rejeição é mostrado ao produtor e enviado por e-mail. "
                    "Preencha antes de usar a ação 'Rejeitar'."
                ),
            },
        ),
        ("Conteúdo", {"fields": ("resumo", "descricao", "imagem", "previa_imagem", "imagem_url")}),
        ("Quando", {"fields": ("data", "data_fim")}),
        ("Onde", {"fields": ("modalidade", "local", "local_ref", "endereco", "regiao", "cidade", "coordenadas")}),
        ("Ingressos", {"fields": ("gratuito", "preco", "capacidade", "limite_por_usuario", "ocupacao", "link_ingressos")}),
        ("Origem", {"fields": ("organizador", "produtor", "criado_por", "fonte", "id_externo", "link_original")}),
        ("Métricas", {"fields": ("visualizacoes", "criado_em", "atualizado_em")}),
    )

    @admin.display(description="Prévia")
    def previa_imagem(self, obj):
        url = obj.imagem_exibicao
        if not url:
            return "—"
        return format_html('<img src="{}" height="160" alt="Prévia da capa">', url)

    @admin.display(description="Coordenadas")
    def coordenadas(self, obj):
        if not obj.tem_coordenadas:
            return "— (vêm do local cadastrado, depois de geocodificado)"
        return f"{obj.latitude}, {obj.longitude}"

    @admin.display(description="Reservas")
    def ocupacao(self, obj):
        if not obj.pk:
            return "—"
        confirmados = obj.ingressos_confirmados
        if obj.capacidade is None:
            return f"{confirmados} (sem limite)"
        return f"{confirmados}/{obj.capacidade}"

    # -- ações de moderação ------------------------------------------------
    # Usam laço em vez de queryset.update() de propósito: cada evento precisa
    # de e-mail e de publicado_em. Os lotes de moderação são pequenos.

    @admin.action(description="Publicar no site (avisa o produtor)")
    def publicar(self, request, queryset):
        publicados = 0
        for evento in queryset.select_related("criado_por", "produtor"):
            if evento.status == Evento.Status.PUBLICADO:
                continue
            evento.status = Evento.Status.PUBLICADO
            evento.publicado_em = evento.publicado_em or timezone.now()
            evento.motivo_rejeicao = ""
            evento.save(update_fields=["status", "publicado_em", "motivo_rejeicao"])
            emails.evento_publicado(
                evento, request.build_absolute_uri(evento.get_absolute_url())
            )
            publicados += 1
        self.message_user(request, f"{publicados} evento(s) publicado(s) e produtor(es) avisado(s).")

    @admin.action(description="Rejeitar (avisa o produtor com o motivo)")
    def rejeitar(self, request, queryset):
        rejeitados, sem_motivo = 0, 0
        for evento in queryset.select_related("criado_por", "produtor"):
            evento.status = Evento.Status.REJEITADO
            evento.publicado_em = None
            evento.save(update_fields=["status", "publicado_em"])
            if not evento.motivo_rejeicao:
                sem_motivo += 1
            emails.evento_rejeitado(
                evento,
                url_absoluta=request.build_absolute_uri(evento.get_absolute_url()),
            )
            rejeitados += 1
        self.message_user(request, f"{rejeitados} evento(s) rejeitado(s).")
        if sem_motivo:
            self.message_user(
                request,
                f"{sem_motivo} evento(s) foram rejeitados sem motivo preenchido. "
                "O produtor recebeu um aviso genérico e não vai saber o que corrigir.",
                messages.WARNING,
            )

    @admin.action(description="Arquivar (tira do site sem apagar)")
    def arquivar(self, request, queryset):
        total = queryset.update(status=Evento.Status.ARQUIVADO)
        self.message_user(request, f"{total} evento(s) arquivado(s).")

    @admin.action(description="Marcar como destaque")
    def marcar_destaque(self, request, queryset):
        total = queryset.update(destaque=True)
        self.message_user(request, f"{total} evento(s) em destaque.")

    @admin.action(description="Remover destaque")
    def remover_destaque(self, request, queryset):
        total = queryset.update(destaque=False)
        self.message_user(request, f"{total} evento(s) sem destaque.")


# =========================
# INGRESSOS E FAVORITOS
# =========================

@admin.register(Ingresso)
class IngressoAdmin(admin.ModelAdmin):
    list_display = ("codigo_curto", "evento", "usuario", "tipo", "status", "valor", "data_compra")
    list_filter = ("status", "tipo", "data_compra")
    search_fields = ("evento__nome", "usuario__email", "codigo")
    autocomplete_fields = ("evento", "usuario")
    list_select_related = ("evento", "usuario")
    readonly_fields = ("codigo", "data_compra", "utilizado_em", "cancelado_em")
    date_hierarchy = "data_compra"

    @admin.display(description="Código")
    def codigo_curto(self, obj):
        return obj.codigo_curto


@admin.register(Favorito)
class FavoritoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "evento", "criado_em")
    search_fields = ("usuario__email", "evento__nome")
    autocomplete_fields = ("usuario", "evento")
    list_select_related = ("usuario", "evento")


@admin.register(AceiteDeTermos)
class AceiteDeTermosAdmin(admin.ModelAdmin):
    """Prova de consentimento. Só leitura: um registro de aceite que pode ser
    editado depois não prova nada."""

    list_display = ("usuario", "versao_termos", "versao_privacidade", "aceito_em", "ip")
    list_filter = ("versao_termos", "aceito_em")
    search_fields = ("usuario__email",)
    list_select_related = ("usuario",)
    readonly_fields = ("usuario", "versao_termos", "versao_privacidade", "aceito_em", "ip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.site_header = "Finde — administração"
admin.site.site_title = "Finde"
admin.site.index_title = "Catálogo e moderação"
