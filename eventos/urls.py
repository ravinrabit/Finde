from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # ---------------- descoberta ----------------
    path("eventos/", views.lista_eventos, name="lista_eventos"),
    path("eventos/hoje/", views.eventos_hoje, name="eventos_hoje"),
    path("eventos/fim-de-semana/", views.eventos_fim_de_semana, name="eventos_fim_de_semana"),
    path("eventos/gratuitos/", views.eventos_gratuitos, name="eventos_gratuitos"),
    # Páginas de faceta com caminho próprio, não querystring: só assim viram
    # páginas indexáveis com título, texto e canônica próprios.
    path("eventos/categoria/<slug:valor>/", views.eventos_por_categoria, name="eventos_categoria"),
    path("eventos/regiao/<slug:valor>/", views.eventos_por_regiao, name="eventos_regiao"),

    path("mapa/", views.mapa_eventos, name="mapa_eventos"),
    path("mapa/dados/", views.mapa_dados, name="mapa_dados"),
    path("agenda.ics", views.agenda_ics, name="agenda_ics"),

    # ---------------- evento ----------------
    # O conversor <slug> também casa com dígitos, então a rota por id vem primeiro,
    # senão /evento/123/ cairia em evento_detalhe e o redirect legado nunca rodaria.
    path("evento/<int:pk>/", views.evento_por_id, name="evento_por_id"),
    path("evento/<slug:slug>/", views.evento_detalhe, name="evento_detalhe"),
    path("evento/<slug:slug>/agenda.ics", views.evento_ics, name="evento_ics"),
    path("evento/<slug:slug>/reservar/", views.reservar_ingresso, name="reservar_ingresso"),
    path("evento/<slug:slug>/favoritar/", views.alternar_favorito, name="alternar_favorito"),
    path("evento/<slug:slug>/editar/", views.editar_evento, name="editar_evento"),
    path("evento/<slug:slug>/inscritos/", views.inscritos_do_evento, name="inscritos_do_evento"),

    # ---------------- locais e produtores ----------------
    path("locais/", views.lista_locais, name="lista_locais"),
    path("local/<slug:slug>/", views.local_detalhe, name="local_detalhe"),
    path("produtores/", views.lista_produtores, name="lista_produtores"),
    path("produtor/<slug:slug>/", views.produtor_detalhe, name="produtor_detalhe"),

    # ---------------- área do produtor ----------------
    path("criar-evento/", views.criar_evento, name="criar_evento"),
    path("criar-evento/colar-link/", views.colar_link, name="colar_link"),
    path("meus-eventos/", views.meus_eventos, name="meus_eventos"),
    path("meus-eventos/perfil/", views.perfil_produtor, name="perfil_produtor"),

    # ---------------- ingressos e favoritos ----------------
    path("meus-ingressos/", views.meus_ingressos, name="meus_ingressos"),
    path("ingresso/<uuid:codigo>/cancelar/", views.cancelar_ingresso, name="cancelar_ingresso"),
    path("ingresso/<uuid:codigo>/validar/", views.validar_ingresso, name="validar_ingresso"),
    path("favoritos/", views.meus_favoritos, name="meus_favoritos"),

    # ---------------- conta e privacidade ----------------
    path("conta/criar/", views.cadastro, name="cadastro"),
    path("conta/privacidade/", views.minha_privacidade, name="minha_privacidade"),
    path("conta/privacidade/exportar/", views.exportar_meus_dados, name="exportar_meus_dados"),
    path("conta/privacidade/excluir/", views.excluir_minha_conta, name="excluir_minha_conta"),

    # ---------------- institucional ----------------
    path("offline/", views.pagina_offline, name="pagina_offline"),
    path("ajuda/", views.pagina_ajuda, name="ajuda"),
    path("contato/", views.pagina_contato, name="contato"),
    path("sobre/", views.pagina_sobre, name="sobre"),
    path("termos/", views.pagina_termos, name="termos"),
    path("privacidade/", views.pagina_privacidade, name="privacidade"),

    # ---------------- infraestrutura ----------------
    path("saude/", views.health_check, name="health_check"),
    path("saude/detalhado/", views.health_check_detalhado, name="health_check_detalhado"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="manifest.webmanifest", content_type="application/manifest+json"
        ),
        name="manifest",
    ),
    path(
        # Precisa ficar na raiz do site (não em /static/) para o escopo do
        # service worker cobrir todas as páginas, não só os arquivos estáticos.
        "sw.js",
        TemplateView.as_view(template_name="sw.js", content_type="application/javascript"),
        name="service_worker",
    ),
]
