from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from .constants import Categoria, Regiao
from .models import Evento, Local, Produtor


class EventoSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.9
    limit = 1000

    def items(self):
        return Evento.objects.visiveis().order_by("data")

    def lastmod(self, obj):
        return obj.atualizado_em


class PaginasEstaticasSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return [
            "home", "lista_eventos", "eventos_hoje", "eventos_fim_de_semana",
            "eventos_gratuitos", "mapa_eventos", "lista_locais", "lista_produtores",
            "sobre", "ajuda", "contato", "termos", "privacidade",
        ]

    def location(self, item):
        return reverse(item)


class CategoriaSitemap(Sitemap):
    """Uma URL por categoria — /eventos/categoria/<slug>/.

    Antes, o sitemap listava 52 variações de querystring sobre a MESMA página,
    todas com o mesmo <title> e o mesmo <h1>. Para o Google isso é conteúdo
    duplicado em massa, o oposto do que se queria. Agora cada faceta tem
    caminho, título, texto de abertura e canônica próprios.

    Só entram categorias que realmente têm evento: página de faceta vazia é
    página fraca.
    """

    changefreq = "daily"
    priority = 0.8

    def items(self):
        com_evento = set(
            Evento.objects.visiveis().exclude(categoria="").values_list("categoria", flat=True)
        )
        return [c.value for c in Categoria if c.value in com_evento]

    def location(self, item):
        return reverse("eventos_categoria", args=[item])


class RegiaoSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        com_evento = set(
            Evento.objects.visiveis().exclude(regiao="").values_list("regiao", flat=True)
        )
        return [r.value for r in Regiao if r.value in com_evento]

    def location(self, item):
        return reverse("eventos_regiao", args=[item])


class LocalSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Local.objects.filter(
            eventos__status=Evento.Status.PUBLICADO, eventos__data__gte=timezone.now()
        ).distinct().order_by("nome")

    def lastmod(self, obj):
        return obj.atualizado_em


class ProdutorSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Produtor.objects.filter(
            eventos__status=Evento.Status.PUBLICADO, eventos__data__gte=timezone.now()
        ).distinct().order_by("nome")

    def lastmod(self, obj):
        return obj.atualizado_em
