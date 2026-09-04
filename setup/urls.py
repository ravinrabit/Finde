from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from eventos.forms import LoginForm
from eventos.ratelimit import limitar
from eventos.sitemaps import (
    CategoriaSitemap,
    EventoSitemap,
    LocalSitemap,
    PaginasEstaticasSitemap,
    ProdutorSitemap,
    RegiaoSitemap,
)

SITEMAPS = {
    "paginas": PaginasEstaticasSitemap,
    "eventos": EventoSitemap,
    "categorias": CategoriaSitemap,
    "regioes": RegiaoSitemap,
    "locais": LocalSitemap,
    "produtores": ProdutorSitemap,
}

# Login e recuperação de senha são os alvos clássicos de força bruta. O limite
# é aplicado aqui, envolvendo a view do Django, para não precisar reimplementar
# nada de autenticação.
login_view = limitar("login")(
    auth.LoginView.as_view(
        template_name="conta/login.html",
        authentication_form=LoginForm,
        redirect_authenticated_user=True,
    )
)

reset_view = limitar("senha_reset")(
    auth.PasswordResetView.as_view(
        template_name="conta/senha-recuperar.html",
        email_template_name="conta/email-senha.txt",
        subject_template_name="conta/email-senha-assunto.txt",
        success_url="/conta/senha/enviado/",
    )
)

# Todo o fluxo de autenticação usa o mesmo layout de duas colunas.
contas = [
    path("entrar/", login_view, name="login"),
    path("sair/", auth.LogoutView.as_view(), name="logout"),
    path("senha/", reset_view, name="password_reset"),
    path(
        "senha/enviado/",
        auth.PasswordResetDoneView.as_view(template_name="conta/senha-enviado.html"),
        name="password_reset_done",
    ),
    path(
        "senha/<uidb64>/<token>/",
        auth.PasswordResetConfirmView.as_view(
            template_name="conta/senha-nova.html",
            success_url="/conta/senha/concluido/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "senha/concluido/",
        auth.PasswordResetCompleteView.as_view(template_name="conta/senha-concluido.html"),
        name="password_reset_complete",
    ),
    path(
        "senha/alterar/",
        auth.PasswordChangeView.as_view(
            template_name="conta/senha-alterar.html",
            success_url="/conta/senha/alterada/",
        ),
        name="password_change",
    ),
    path(
        "senha/alterada/",
        auth.PasswordChangeDoneView.as_view(template_name="conta/senha-alterada.html"),
        name="password_change_done",
    ),
]

urlpatterns = [
    # O caminho do admin é configurável (ADMIN_URL). Tirar o /admin/ do lugar
    # óbvio não substitui autenticação, mas elimina o ruído das varreduras
    # automatizadas que batem em /admin/ o dia inteiro.
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
    path("conta/", include(contas)),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": SITEMAPS},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("", include("eventos.urls")),
]

handler403 = "eventos.views.erro_403"
handler404 = "eventos.views.erro_404"
handler500 = "eventos.views.erro_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
