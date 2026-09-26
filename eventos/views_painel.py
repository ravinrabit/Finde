from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import emails
from .constants import DIAS_DESTAQUE_PADRAO
from .decorators import staff_requerido
from .forms import EventoPainelForm, LocalForm, ProdutorPainelForm
from .models import Evento, Local, Produtor, SolicitacaoDestaque
from .services import catalogo, moderacao
from .services import painel as servico_painel
from .views import gerar_variantes_de_capa, paginar

EVENTOS_POR_PAGINA_PAINEL = 20
PRODUTORES_POR_PAGINA_PAINEL = 20
LOCAIS_POR_PAGINA_PAINEL = 20


@staff_requerido
def dashboard(request):
    return render(request, "eventos/painel/dashboard.html", {
        "estatisticas": servico_painel.estatisticas_gerais(),
        "eventos_pendentes": servico_painel.previa_pendentes(),
        "produtores_pendentes": servico_painel.previa_produtores_pendentes(),
    })


@staff_requerido
def moderacao_view(request):
    status = request.GET.get("status", Evento.Status.PENDENTE)
    if status not in Evento.Status.values:
        status = ""
    busca = request.GET.get("busca", "").strip()

    eventos = servico_painel.fila_de_moderacao(status=status, busca=busca)

    return render(request, "eventos/painel/moderacao.html", {
        "status_atual": status,
        "busca": busca,
        "status_opcoes": Evento.Status.choices,
        "pagina": paginar(request, eventos, EVENTOS_POR_PAGINA_PAINEL),
    })


@staff_requerido
def evento_criar(request):
    formulario = EventoPainelForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        evento = catalogo.salvar_evento_da_equipe(formulario.save(commit=False))
        gerar_variantes_de_capa(evento)
        messages.success(request, f'"{evento.nome}" foi criado.')
        return redirect("painel_evento_editar", slug=evento.slug)
    return render(request, "eventos/painel/evento-form.html", {
        "form": formulario,
        "evento": None,
        "titulo": "Novo evento",
        "locais_conhecidos": Local.objects.order_by("nome").values_list("nome", flat=True)[:400],
    })


@staff_requerido
def evento_editar(request, slug):
    evento = get_object_or_404(Evento, slug=slug)
    status_anterior = evento.status
    formulario = EventoPainelForm(request.POST or None, request.FILES or None, instance=evento)
    if request.method == "POST" and formulario.is_valid():
        evento = catalogo.salvar_evento_da_equipe(formulario.save(commit=False))
        gerar_variantes_de_capa(evento)
        if evento.status != status_anterior:
            url = request.build_absolute_uri(evento.get_absolute_url())
            if evento.status == Evento.Status.PUBLICADO:
                emails.evento_publicado(evento, url)
            elif evento.status == Evento.Status.REJEITADO:
                emails.evento_rejeitado(evento, motivo=evento.motivo_rejeicao, url_absoluta=url)
        messages.success(request, f'"{evento.nome}" foi atualizado.')
        return redirect("painel_evento_editar", slug=evento.slug)
    return render(request, "eventos/painel/evento-form.html", {
        "form": formulario,
        "evento": evento,
        "titulo": evento.nome,
        "locais_conhecidos": Local.objects.order_by("nome").values_list("nome", flat=True)[:400],
    })


@staff_requerido
@require_POST
def evento_remover(request, slug):
    evento = get_object_or_404(Evento, slug=slug)
    if request.POST.get("confirmacao", "").strip() != evento.nome:
        messages.error(request, "Digite o nome exato do evento para apagar de vez.")
        return redirect("painel_evento_editar", slug=evento.slug)
    nome = evento.nome
    evento.delete()
    messages.success(request, f'"{nome}" foi apagado definitivamente.')
    return redirect("painel_moderacao")


@staff_requerido
@require_POST
def evento_publicar(request, slug):
    evento = get_object_or_404(Evento, slug=slug)
    moderacao.publicar(evento, request=request)
    messages.success(request, f'"{evento.nome}" foi publicado.')
    return redirect(request.POST.get("proximo") or reverse("painel_moderacao"))


@staff_requerido
@require_POST
def evento_rejeitar(request, slug):
    evento = get_object_or_404(Evento, slug=slug)
    motivo = request.POST.get("motivo", "").strip()
    moderacao.rejeitar(evento, motivo=motivo, request=request)
    messages.success(request, f'"{evento.nome}" foi rejeitado.')
    return redirect(request.POST.get("proximo") or reverse("painel_moderacao"))


@staff_requerido
@require_POST
def evento_arquivar(request, slug):
    evento = get_object_or_404(Evento, slug=slug)
    moderacao.arquivar(evento)
    messages.success(request, f'"{evento.nome}" foi arquivado.')
    return redirect(request.POST.get("proximo") or reverse("painel_moderacao"))


@staff_requerido
def produtores_view(request):
    apenas_nao_verificados = request.GET.get("filtro") != "todos"
    busca = request.GET.get("busca", "").strip()

    produtores = servico_painel.produtores_para_revisao(
        apenas_nao_verificados=apenas_nao_verificados, busca=busca
    )

    return render(request, "eventos/painel/produtores.html", {
        "apenas_nao_verificados": apenas_nao_verificados,
        "busca": busca,
        "pagina": paginar(request, produtores, PRODUTORES_POR_PAGINA_PAINEL),
    })


@staff_requerido
def produtor_criar(request):
    formulario = ProdutorPainelForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        produtor = formulario.save()
        messages.success(request, f'"{produtor.nome}" foi criado.')
        return redirect("painel_produtor_editar", slug=produtor.slug)
    return render(request, "eventos/painel/produtor-form.html", {
        "form": formulario,
        "produtor": None,
        "titulo": "Novo produtor",
    })


@staff_requerido
def produtor_editar(request, slug):
    produtor = get_object_or_404(Produtor, slug=slug)
    formulario = ProdutorPainelForm(request.POST or None, request.FILES or None, instance=produtor)
    if request.method == "POST" and formulario.is_valid():
        produtor = formulario.save()
        messages.success(request, f'"{produtor.nome}" foi atualizado.')
        return redirect("painel_produtor_editar", slug=produtor.slug)
    return render(request, "eventos/painel/produtor-form.html", {
        "form": formulario,
        "produtor": produtor,
        "titulo": produtor.nome,
    })


@staff_requerido
@require_POST
def produtor_remover(request, slug):
    produtor = get_object_or_404(Produtor, slug=slug)
    if produtor.eventos.exists():
        messages.error(request, f'"{produtor.nome}" tem eventos vinculados e não pode ser removido.')
        return redirect("painel_produtor_editar", slug=produtor.slug)
    if request.POST.get("confirmacao", "").strip() != produtor.nome:
        messages.error(request, "Digite o nome exato do produtor para apagar de vez.")
        return redirect("painel_produtor_editar", slug=produtor.slug)
    nome = produtor.nome
    produtor.delete()
    messages.success(request, f'"{nome}" foi removido.')
    return redirect("painel_produtores")


@staff_requerido
@require_POST
def produtor_verificar(request, slug):
    produtor = get_object_or_404(Produtor, slug=slug)
    moderacao.verificar_produtor(produtor, verificado=True)
    messages.success(request, f'"{produtor.nome}" foi verificado.')
    return redirect(request.POST.get("proximo") or reverse("painel_produtores"))


@staff_requerido
@require_POST
def produtor_remover_verificacao(request, slug):
    produtor = get_object_or_404(Produtor, slug=slug)
    moderacao.verificar_produtor(produtor, verificado=False)
    messages.success(request, f'Verificação de "{produtor.nome}" foi removida.')
    return redirect(request.POST.get("proximo") or reverse("painel_produtores"))


@staff_requerido
def locais_view(request):
    busca = request.GET.get("busca", "").strip()
    locais = Local.objects.order_by("-criado_em")
    if busca:
        locais = locais.filter(nome__icontains=busca)
    return render(request, "eventos/painel/locais.html", {
        "busca": busca,
        "pagina": paginar(request, locais, LOCAIS_POR_PAGINA_PAINEL),
    })


@staff_requerido
def local_criar(request):
    formulario = LocalForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        local = formulario.save()
        catalogo.geocodificar_se_necessario(local)
        messages.success(request, f'"{local.nome}" foi criado.')
        return redirect("painel_local_editar", slug=local.slug)
    return render(request, "eventos/painel/local-form.html", {
        "form": formulario,
        "local": None,
        "titulo": "Novo local",
    })


@staff_requerido
def local_editar(request, slug):
    local = get_object_or_404(Local, slug=slug)
    formulario = LocalForm(request.POST or None, instance=local)
    if request.method == "POST" and formulario.is_valid():
        local = formulario.save()
        catalogo.geocodificar_se_necessario(local)
        messages.success(request, f'"{local.nome}" foi atualizado.')
        return redirect("painel_local_editar", slug=local.slug)
    return render(request, "eventos/painel/local-form.html", {
        "form": formulario,
        "local": local,
        "titulo": local.nome,
    })


@staff_requerido
@require_POST
def local_remover(request, slug):
    local = get_object_or_404(Local, slug=slug)
    if local.eventos.exists():
        messages.error(request, f'"{local.nome}" tem eventos vinculados e não pode ser removido.')
        return redirect("painel_local_editar", slug=local.slug)
    if request.POST.get("confirmacao", "").strip() != local.nome:
        messages.error(request, "Digite o nome exato do local para apagar de vez.")
        return redirect("painel_local_editar", slug=local.slug)
    nome = local.nome
    local.delete()
    messages.success(request, f'"{nome}" foi apagado.')
    return redirect("painel_locais")


@staff_requerido
def destaques_view(request):
    solicitacoes = (
        SolicitacaoDestaque.objects.filter(atendida=False)
        .select_related("evento")
        .order_by("criado_em")
    )
    return render(request, "eventos/painel/destaques.html", {"solicitacoes": solicitacoes})


@staff_requerido
@require_POST
def destaque_aprovar(request, pk):
    solicitacao = get_object_or_404(SolicitacaoDestaque, pk=pk, atendida=False)
    evento = solicitacao.evento
    agora = timezone.now()

    base = evento.destaque_pago_ate if evento.destaque_pago_ate and evento.destaque_pago_ate > agora else agora
    evento.plano_destaque = solicitacao.plano
    evento.destaque_pago_ate = base + timezone.timedelta(days=DIAS_DESTAQUE_PADRAO)
    evento.save(update_fields=["plano_destaque", "destaque_pago_ate"])
    solicitacao.atendida = True
    solicitacao.atendida_em = timezone.now()
    solicitacao.save(update_fields=["atendida", "atendida_em"])
    messages.success(request, f'Destaque "{solicitacao.get_plano_display()}" ativado para "{evento.nome}".')
    return redirect("painel_destaques")


@staff_requerido
@require_POST
def destaque_recusar(request, pk):
    solicitacao = get_object_or_404(SolicitacaoDestaque, pk=pk, atendida=False)
    solicitacao.atendida = True
    solicitacao.atendida_em = timezone.now()
    solicitacao.save(update_fields=["atendida", "atendida_em"])
    messages.success(request, f'Pedido de "{solicitacao.evento.nome}" recusado.')
    return redirect("painel_destaques")
