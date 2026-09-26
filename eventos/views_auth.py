from django.contrib.auth import login as login_django
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, VerificarTOTPForm
from .models import DispositivoTOTP
from .ratelimit import limitar
from .services import totp

CHAVE_USUARIO_PENDENTE = "2fa_usuario_id"
CHAVE_PROXIMO_PENDENTE = "2fa_proximo"
CHAVE_SEGREDO_PENDENTE = "2fa_segredo_pendente"


class LoginComDoisFatoresView(LoginView):


    template_name = "conta/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        usuario = form.get_user()
        if not usuario.is_staff:
            return super().form_valid(form)

        self.request.session[CHAVE_USUARIO_PENDENTE] = usuario.pk
        self.request.session[CHAVE_PROXIMO_PENDENTE] = self.get_redirect_url() or ""

        dispositivo = getattr(usuario, "dispositivo_totp", None)
        if dispositivo and dispositivo.confirmado:
            return redirect("dois_fatores_verificar")
        return redirect("dois_fatores_configurar")


def _usuario_pendente(request):
    pk = request.session.get(CHAVE_USUARIO_PENDENTE)
    if not pk:
        return None
    try:
        return User.objects.get(pk=pk, is_staff=True)
    except User.DoesNotExist:
        return None


def _concluir_login(request, usuario):
    login_django(request, usuario)
    proximo = request.session.pop(CHAVE_PROXIMO_PENDENTE, "")
    request.session.pop(CHAVE_USUARIO_PENDENTE, None)
    request.session.pop(CHAVE_SEGREDO_PENDENTE, None)
    if not proximo or not url_has_allowed_host_and_scheme(
        proximo, allowed_hosts={request.get_host()}
    ):
        proximo = "home"
    return redirect(proximo)


@limitar("dois_fatores")
def dois_fatores_configurar(request):
    usuario = _usuario_pendente(request)
    if not usuario:
        return redirect("login")

    dispositivo_existente = getattr(usuario, "dispositivo_totp", None)
    if dispositivo_existente and dispositivo_existente.confirmado:
        return redirect("dois_fatores_verificar")

    segredo = request.session.get(CHAVE_SEGREDO_PENDENTE)
    if not segredo:
        segredo = totp.gerar_segredo()
        request.session[CHAVE_SEGREDO_PENDENTE] = segredo

    if request.method == "POST":
        formulario = VerificarTOTPForm(request.POST)
        if formulario.is_valid() and totp.verificar(segredo, formulario.cleaned_data["codigo"]):
            dispositivo = DispositivoTOTP.novo_para(usuario, segredo)
            dispositivo.confirmado = True
            dispositivo.save(update_fields=["confirmado"])
            return _concluir_login(request, usuario)
        formulario.add_error("codigo", "Código incorreto. Confira o app e tente de novo.")
    else:
        formulario = VerificarTOTPForm()

    return render(request, "conta/2fa-configurar.html", {
        "form": formulario,
        "segredo": segredo,
        "qr_base64": totp.qr_code_base64(totp.uri_provisionamento(segredo, usuario.email or usuario.username)),
    })


@limitar("dois_fatores")
def dois_fatores_verificar(request):
    usuario = _usuario_pendente(request)
    if not usuario:
        return redirect("login")

    dispositivo = getattr(usuario, "dispositivo_totp", None)
    if not dispositivo or not dispositivo.confirmado:
        return redirect("dois_fatores_configurar")

    if request.method == "POST":
        formulario = VerificarTOTPForm(request.POST)
        if formulario.is_valid() and totp.verificar(dispositivo.segredo(), formulario.cleaned_data["codigo"]):
            return _concluir_login(request, usuario)
        formulario.add_error("codigo", "Código incorreto.")
    else:
        formulario = VerificarTOTPForm()

    return render(request, "conta/2fa-verificar.html", {"form": formulario})
