import json
import logging
import secrets
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as autenticar
from django.contrib.auth import logout as encerrar_sessao
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST

from .constants import (
    BENEFICIOS_POR_PLANO,
    CENTRO_DF,
    DESCRICAO_POR_CATEGORIA,
    DESCRICAO_POR_REGIAO,
    ICONE_PADRAO,
    ICONE_POR_CATEGORIA,
    PRECO_POR_PLANO,
    REGIOES_EM_DESTAQUE,
    Categoria,
    PlanoDestaque,
    Regiao,
)
from .forms import (
    CadastroForm,
    ColarLinkForm,
    EventoForm,
    EventoPublicoForm,
    ExclusaoDeContaForm,
    FiltroEventosForm,
    ProdutorForm,
    SolicitacaoDestaqueForm,
)
from .models import Evento, Favorito, Ingresso, Local, Produtor, SolicitacaoDestaque
from .ratelimit import excedeu, ip_do_pedido, limitar, resposta_429
from .services import busca as servico_busca
from .services import calendario, catalogo, lgpd, reservas
from .templatetags.finde import TRACADOS

logger = logging.getLogger("eventos")

EVENTOS_POR_PAGINA = 12
LOCAIS_POR_PAGINA = 24
INGRESSOS_POR_PAGINA = 20
MAX_EVENTOS_NO_MAPA = 300
MAX_PARA_ORDENAR_DISTANCIA = 500
JANELA_VISUALIZACAO = 60 * 30


def cache_para_anonimos(segundos):
    """cache_page, mas só entra em ação pra quem não está logado.

    Visitante anônimo vê sempre o mesmo tanto de favorito (nenhum) e o
    mesmo menu — pode compartilhar a página cacheada com outro anônimo
    sem vazar nada de ninguém. Quem está logado sempre renderiza na hora,
    pra ver os próprios favoritos e o menu de conta certos.
    """

    def decorador(view):
        view_cacheada = cache_page(segundos)(view)

        @wraps(view)
        def envelope(request, *args, **kwargs):
            if not getattr(settings, "CACHE_PAGINA_ATIVO", True) or request.user.is_authenticated:
                return view(request, *args, **kwargs)
            return view_cacheada(request, *args, **kwargs)

        return envelope

    return decorador


# =========================
# DESCOBERTA
# =========================

@cache_para_anonimos(180)
def home(request):
    visiveis = Evento.objects.visiveis().para_cards()

    destaques = list(visiveis.filter(destaque=True).com_capa()[:3])
    if not destaques:
        destaques = list(visiveis.com_capa()[:3])
    ids_destaque = [e.pk for e in destaques]

    inicio_fds, fim_fds = Evento.janela_fim_de_semana()

    return render(request, "eventos/home.html", {
        "destaque_principal": destaques[0] if destaques else None,
        "destaques_secundarios": destaques[1:],
        "em_breve": visiveis.exclude(pk__in=ids_destaque)[:8],
        "fim_de_semana": visiveis.entre(inicio_fds, fim_fds)[:4],
        "gratuitos": visiveis.filter(Q(gratuito=True) | Q(preco=0))[:4],
        "categorias": categorias_com_contagem(),
        "regioes": regioes_com_contagem(),
        "total_eventos": visiveis.count(),
        "total_categorias": visiveis.exclude(categoria="").values("categoria").distinct().count(),
        "favoritos_do_usuario": ids_favoritos(request.user),
        "janela_fds": (inicio_fds, fim_fds),
    })


def categorias_com_contagem(limite=12):
    contagens = cache.get("home:categorias")
    if contagens is None:
        contagens = dict(
            Evento.objects.visiveis()
            .exclude(categoria="")
            .values_list("categoria")
            .annotate(total=Count("id"))
        )
        cache.set("home:categorias", contagens, 300)
    rotulos = dict(Categoria.choices)
    categorias = [
        {
            "valor": valor,
            "nome": rotulos[valor],
            "icone": ICONE_POR_CATEGORIA.get(valor, ICONE_PADRAO),
            "total": total,
            "url": reverse("eventos_categoria", args=[valor]),
        }
        for valor, total in contagens.items()
        if valor in rotulos
    ]
    return sorted(categorias, key=lambda c: (-c["total"], c["nome"]))[:limite]


def regioes_com_contagem(apenas_destaque=True):
    contagens = cache.get("home:regioes")
    if contagens is None:
        contagens = dict(
            Evento.objects.visiveis()
            .exclude(regiao="")
            .values_list("regiao")
            .annotate(total=Count("id"))
        )
        cache.set("home:regioes", contagens, 300)
    rotulos = dict(Regiao.choices)
    alvo = REGIOES_EM_DESTAQUE if apenas_destaque else list(Regiao)
    regioes = [
        {
            "valor": r.value,
            "nome": rotulos[r.value],
            "total": contagens.get(r.value, 0),
            "url": reverse("eventos_regiao", args=[r.value]),
        }
        for r in alvo
    ]
    return sorted(regioes, key=lambda r: -r["total"])


@cache_para_anonimos(180)
def lista_eventos(request, contexto_extra=None, base=None, formulario=None):
    # As views de categoria/região/hoje/etc. chamam a versão sem cache
    # diretamente (_lista_eventos), porque cada uma já tem seu próprio
    # cache_para_anonimos — cachear aqui de novo seria cache duplicado
    # competindo pela mesma chave (a chave é o caminho da requisição, que
    # nessas chamadas internas continua sendo o da view de fora).
    return _lista_eventos(request, contexto_extra, base, formulario)


def _lista_eventos(request, contexto_extra=None, base=None, formulario=None):
    if excedeu("busca", request) and request.GET.get("q"):
        return resposta_429(request, "Muitas buscas seguidas. Espere um instante.")

    formulario = formulario or FiltroEventosForm(request.GET or None)
    base = Evento.objects.visiveis() if base is None else base
    eventos, coordenadas, ordenar_por_distancia = aplicar_filtros(base.para_cards(), formulario)

    if ordenar_por_distancia:
        candidatos = list(eventos[:MAX_PARA_ORDENAR_DISTANCIA])
        anotar_distancias(candidatos, coordenadas)
        pagina = paginar(request, candidatos, EVENTOS_POR_PAGINA)
        itens = list(pagina.object_list)
    else:
        pagina = paginar(request, eventos, EVENTOS_POR_PAGINA)
        itens = list(pagina.object_list)
        if coordenadas:
            anotar_distancias(itens, coordenadas)

    contexto = {
        "form": formulario,
        "pagina": pagina,
        "eventos": itens,
        "total": pagina.paginator.count,
        "filtros_ativos": formulario.filtros_ativos,
        "favoritos_do_usuario": ids_favoritos(request.user),
        "centro_mapa": coordenadas or CENTRO_DF,
        "titulo_pagina": "Agenda de Brasília",
        "descricao_pagina": (
            "Tudo o que está confirmado no Distrito Federal. Filtre por região, "
            "data, preço e distância."
        ),
    }
    contexto.update(contexto_extra or {})
    return render(request, "eventos/lista-eventos.html", contexto)


def aplicar_filtros(eventos, formulario):
    formulario.is_valid()

    eventos = servico_busca.aplicar(eventos, formulario.valor("q"))

    if categoria := formulario.valor("categoria"):
        eventos = eventos.filter(categoria=categoria)

    if regiao := formulario.valor("regiao"):
        eventos = eventos.filter(regiao=regiao)

    intervalo = formulario.intervalo()
    if intervalo:
        eventos = eventos.entre(*intervalo)
    elif periodo := formulario.valor("periodo"):
        eventos = filtrar_por_periodo(eventos, periodo)

    preco = formulario.valor("preco")
    if preco == "gratuito":
        eventos = eventos.filter(Q(gratuito=True) | Q(preco=0))
    elif preco == "ate-50":
        eventos = eventos.filter(gratuito=False, preco__gt=0, preco__lte=50)
    elif preco == "50-150":
        eventos = eventos.filter(gratuito=False, preco__gt=50, preco__lte=150)
    elif preco == "acima-150":
        eventos = eventos.filter(gratuito=False, preco__gt=150)

    acessos = formulario.valor("acesso")
    if "acessivel" in acessos:
        eventos = eventos.filter(local_ref__acessivel_cadeirante=True)
    if "estacionamento" in acessos:
        eventos = eventos.filter(local_ref__estacionamento=True)
    if "metro" in acessos:
        eventos = eventos.filter(
            local_ref__metro_distancia_m__lte=settings.METRO_RAIO_PADRAO_M
            if hasattr(settings, "METRO_RAIO_PADRAO_M")
            else 1000
        )

    coordenadas = formulario.coordenadas()
    raio = formulario.valor("raio")
    if coordenadas and raio:
        try:
            eventos = eventos.no_raio(coordenadas[0], coordenadas[1], float(raio))
        except (TypeError, ValueError):
            pass

    ordenar = formulario.valor("ordenar")
    if ordenar == "preco":
        return eventos.order_by("-gratuito", F("preco").asc(nulls_last=True), "data"), coordenadas, False
    if ordenar == "recentes":
        return eventos.order_by(F("criado_em").desc(nulls_last=True), "data"), coordenadas, False
    if ordenar == "distancia" and coordenadas:
        return eventos.com_coordenadas().order_by("data"), coordenadas, True
    if formulario.valor("q") and connection.vendor == "postgresql":
        return servico_busca.ordenar_por_relevancia(eventos), coordenadas, False
    return eventos.com_rank_destaque().order_by("-rank_destaque_db", "data"), coordenadas, False


def anotar_distancias(itens, coordenadas):
    lat, lon = coordenadas
    for evento in itens:
        evento.distancia = evento.distancia_de(lat, lon)
    itens.sort(key=lambda e: (e.distancia is None, e.distancia or 0, e.data))


def filtrar_por_periodo(eventos, periodo):
    agora = timezone.localtime()
    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)

    if periodo == "hoje":
        return eventos.entre(agora, inicio_dia + timedelta(days=1))
    if periodo == "amanha":
        amanha = inicio_dia + timedelta(days=1)
        return eventos.entre(amanha, amanha + timedelta(days=1))
    if periodo == "fim-de-semana":
        return eventos.entre(*Evento.janela_fim_de_semana())
    if periodo == "semana":
        return eventos.entre(agora, agora + timedelta(days=7))
    if periodo == "mes":
        return eventos.entre(agora, agora + timedelta(days=30))
    return eventos


# ---- páginas de faceta indexáveis (SEO) ----

@cache_para_anonimos(180)
def eventos_por_categoria(request, valor):
    if valor not in {c.value for c in Categoria}:
        raise Http404("Categoria não encontrada.")
    rotulo = dict(Categoria.choices)[valor]
    dados = request.GET.copy()
    dados["categoria"] = valor
    return _lista_eventos(
        request,
        formulario=FiltroEventosForm(dados),
        contexto_extra={
            "faceta": {"tipo": "categoria", "valor": valor, "nome": rotulo},
            "titulo_pagina": f"{rotulo} em Brasília",
            "descricao_pagina": DESCRICAO_POR_CATEGORIA.get(valor, ""),
            "canonica": request.build_absolute_uri(reverse("eventos_categoria", args=[valor])),
        },
    )


@cache_para_anonimos(180)
def eventos_por_regiao(request, valor):
    if valor not in {r.value for r in Regiao}:
        raise Http404("Região não encontrada.")
    rotulo = dict(Regiao.choices)[valor]
    dados = request.GET.copy()
    dados["regiao"] = valor
    return _lista_eventos(
        request,
        formulario=FiltroEventosForm(dados),
        contexto_extra={
            "faceta": {"tipo": "regiao", "valor": valor, "nome": rotulo},
            "titulo_pagina": f"Eventos em {rotulo}",
            "descricao_pagina": DESCRICAO_POR_REGIAO.get(
                valor, f"O que está acontecendo em {rotulo}, no Distrito Federal."
            ),
            "canonica": request.build_absolute_uri(reverse("eventos_regiao", args=[valor])),
        },
    )


@cache_para_anonimos(180)
def eventos_gratuitos(request):
    dados = request.GET.copy()
    dados["preco"] = "gratuito"
    return _lista_eventos(
        request,
        formulario=FiltroEventosForm(dados),
        contexto_extra={
            "faceta": {"tipo": "preco", "valor": "gratuito", "nome": "Gratuitos"},
            "titulo_pagina": "Eventos gratuitos em Brasília",
            "descricao_pagina": (
                "Programação aberta ao público no DF: Eixão do Lazer, shows na Esplanada, "
                "exposições, feiras e cinema de graça."
            ),
            "canonica": request.build_absolute_uri(reverse("eventos_gratuitos")),
        },
    )


@cache_para_anonimos(60)
def eventos_hoje(request):
    dados = request.GET.copy()
    dados["periodo"] = "hoje"
    return _lista_eventos(
        request,
        formulario=FiltroEventosForm(dados),
        contexto_extra={
            "faceta": {"tipo": "periodo", "valor": "hoje", "nome": "Hoje"},
            "titulo_pagina": "O que fazer hoje em Brasília",
            "descricao_pagina": "A agenda de hoje no Distrito Federal, atualizada ao longo do dia.",
            "canonica": request.build_absolute_uri(reverse("eventos_hoje")),
        },
    )


@cache_para_anonimos(60)
def eventos_fim_de_semana(request):
    dados = request.GET.copy()
    dados["periodo"] = "fim-de-semana"
    inicio, fim = Evento.janela_fim_de_semana()
    return _lista_eventos(
        request,
        formulario=FiltroEventosForm(dados),
        contexto_extra={
            "faceta": {"tipo": "periodo", "valor": "fim-de-semana", "nome": "Fim de semana"},
            "titulo_pagina": "O que fazer neste fim de semana em Brasília",
            "descricao_pagina": (
                "De sexta à noite até domingo: shows, feiras, teatro e programação gratuita no DF."
            ),
            "janela_fds": (inicio, fim),
            "canonica": request.build_absolute_uri(reverse("eventos_fim_de_semana")),
        },
    )


# ---- mapa ----

def mapa_eventos(request):
    formulario = FiltroEventosForm(request.GET or None)
    eventos, coordenadas, _ = aplicar_filtros(
        Evento.objects.visiveis().com_coordenadas().para_cards(), formulario
    )
    return render(request, "eventos/mapa.html", {
        "form": formulario,
        "filtros_ativos": formulario.filtros_ativos,
        "total": eventos.count(),
        "centro_mapa": coordenadas or CENTRO_DF,
        "url_dados": reverse("mapa_dados"),
        "titulo_pagina": "Mapa de eventos de Brasília",
    })


def mapa_dados(request):
    formulario = FiltroEventosForm(request.GET or None)
    eventos, _, _ = aplicar_filtros(
        Evento.objects.visiveis().com_coordenadas().para_cards(), formulario
    )
    recursos = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(e.longitude), float(e.latitude)]},
            "properties": {
                "nome": e.nome,
                "url": e.get_absolute_url(),
                "local": e.local,
                "quando": timezone.localtime(e.data).strftime("%d/%m %H:%M"),
                "preco": e.preco_rotulo,
                "categoria": e.get_categoria_display() if e.categoria else "",
                "icone": TRACADOS.get(
                    ICONE_POR_CATEGORIA.get(e.categoria, ICONE_PADRAO), TRACADOS[ICONE_PADRAO]
                ),
                "imagem": e.imagem_exibicao,
                "aproximado": bool(e.local_ref and e.local_ref.coordenada_aproximada),
            },
        }
        for e in eventos[:MAX_EVENTOS_NO_MAPA]
    ]
    return JsonResponse({"type": "FeatureCollection", "features": recursos})


# ---- detalhe ----

def evento_detalhe(request, slug):
    evento = get_object_or_404(
        Evento.objects.select_related("criado_por", "local_ref", "produtor"), slug=slug
    )

    e_dono = request.user.is_authenticated and evento.criado_por_id == request.user.id
    if evento.status != Evento.Status.PUBLICADO and not (e_dono or request.user.is_staff):
        raise Http404("Evento não encontrado.")

    if evento.status == Evento.Status.PUBLICADO:
        contar_visualizacao(request, evento)

    # Sem esse guarda, um evento sem categoria e sem região "combinaria" com
    # todos os outros que também estivessem em branco.
    semelhanca = Q(pk__in=[])
    if evento.categoria:
        semelhanca |= Q(categoria=evento.categoria)
    if evento.regiao:
        semelhanca |= Q(regiao=evento.regiao)

    relacionados = (
        Evento.objects.visiveis().para_cards().exclude(pk=evento.pk).filter(semelhanca)[:4]
    )

    do_produtor = Evento.objects.none()
    if evento.produtor_id:
        do_produtor = (
            Evento.objects.visiveis().para_cards().exclude(pk=evento.pk)
            .filter(produtor_id=evento.produtor_id)[:4]
        )
    elif evento.organizador:
        do_produtor = (
            Evento.objects.visiveis().para_cards().exclude(pk=evento.pk)
            .filter(organizador__iexact=evento.organizador)[:4]
        )

    no_local = Evento.objects.none()
    if evento.local_ref_id:
        no_local = (
            Evento.objects.visiveis().para_cards().exclude(pk=evento.pk)
            .filter(local_ref_id=evento.local_ref_id)[:4]
        )

    url_absoluta = request.build_absolute_uri(evento.get_absolute_url())

    return render(request, "eventos/evento-detalhe.html", {
        "evento": evento,
        "e_dono": e_dono,
        "relacionados": relacionados,
        "do_produtor": do_produtor,
        "no_local": no_local,
        "e_favorito": evento.pk in ids_favoritos(request.user),
        "valor_inteira": evento.valor_para(Ingresso.Tipo.INTEIRA),
        "valor_meia": evento.valor_para(Ingresso.Tipo.MEIA),
        "preco_definido": evento.gratuito or evento.preco is not None,
        "vagas": evento.vagas_disponiveis,
        "link_google_agenda": calendario.link_google_agenda(evento, url_absoluta),
        "canonica": url_absoluta,
    })


def contar_visualizacao(request, evento):
    if not request.session.session_key:
        request.session.save()
    chave = f"visto:{evento.pk}"
    agora = timezone.now().timestamp()
    ultimo = request.session.get(chave)
    if ultimo and agora - ultimo < JANELA_VISUALIZACAO:
        return
    request.session[chave] = agora
    evento.registrar_visualizacao()


def evento_por_id(request, pk):
    evento = get_object_or_404(Evento, pk=pk, status=Evento.Status.PUBLICADO)
    return redirect(evento, permanent=True)


def evento_ics(request, slug):
    evento = get_object_or_404(Evento, slug=slug, status=Evento.Status.PUBLICADO)
    conteudo = calendario.calendario(
        [evento],
        url_de=lambda e: request.build_absolute_uri(e.get_absolute_url()),
        nome=settings.SITE_NOME,
        dominio=settings.SITE_DOMINIO,
    )
    resposta = HttpResponse(conteudo, content_type="text/calendar; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{calendario.nome_de_arquivo(evento)}"'
    return resposta


def agenda_ics(request):
    formulario = FiltroEventosForm(request.GET or None)
    eventos, _, _ = aplicar_filtros(Evento.objects.visiveis(), formulario)
    conteudo = calendario.calendario(
        eventos[:200],
        url_de=lambda e: request.build_absolute_uri(e.get_absolute_url()),
        nome=f"{settings.SITE_NOME} — agenda de Brasília",
        dominio=settings.SITE_DOMINIO,
    )
    resposta = HttpResponse(conteudo, content_type="text/calendar; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="finde-agenda.ics"'
    return resposta


# =========================
# LOCAIS
# =========================

def lista_locais(request):
    locais = (
        Local.objects.annotate(
            total=Count(
                "eventos",
                filter=Q(eventos__status=Evento.Status.PUBLICADO, eventos__data__gte=timezone.now()),
            )
        )
        .filter(total__gt=0)
        .order_by("-total", "nome")
    )
    if regiao := request.GET.get("regiao"):
        if regiao in {r.value for r in Regiao}:
            locais = locais.filter(regiao=regiao)
    return render(request, "eventos/lista-locais.html", {
        "pagina": paginar(request, locais, LOCAIS_POR_PAGINA),
        "total": locais.count(),
        "regioes": regioes_com_contagem(apenas_destaque=False),
        "regiao_ativa": request.GET.get("regiao", ""),
    })


def local_detalhe(request, slug):
    local = get_object_or_404(Local, slug=slug)
    proximos = (
        Evento.objects.visiveis().para_cards().filter(local_ref=local).order_by("data")
    )
    coordenadas = local.coordenadas_ou_centroide()

    proximos_do_local = Local.objects.none()
    if local.tem_coordenadas:
        proximos_do_local = (
            Local.objects.com_coordenadas()
            .exclude(pk=local.pk)
            .filter(regiao=local.regiao)
            .annotate(
                total=Count(
                    "eventos",
                    filter=Q(
                        eventos__status=Evento.Status.PUBLICADO, eventos__data__gte=timezone.now()
                    ),
                )
            )
            .filter(total__gt=0)[:6]
        )

    return render(request, "eventos/local-detalhe.html", {
        "local": local,
        "pagina": paginar(request, proximos, EVENTOS_POR_PAGINA),
        "total": proximos.count(),
        "coordenadas": coordenadas,
        "locais_vizinhos": proximos_do_local,
        "favoritos_do_usuario": ids_favoritos(request.user),
        "canonica": request.build_absolute_uri(local.get_absolute_url()),
    })


# =========================
# PRODUTORES
# =========================

def lista_produtores(request):
    produtores = (
        Produtor.objects.annotate(
            total=Count(
                "eventos",
                filter=Q(eventos__status=Evento.Status.PUBLICADO, eventos__data__gte=timezone.now()),
            )
        )
        .filter(total__gt=0)
        .order_by("-verificado", "-total", "nome")
    )
    return render(request, "eventos/lista-produtores.html", {
        "pagina": paginar(request, produtores, LOCAIS_POR_PAGINA),
        "total": produtores.count(),
    })


def produtor_detalhe(request, slug):
    produtor = get_object_or_404(Produtor, slug=slug)
    agora = timezone.now()
    proximos = (
        Evento.objects.visiveis().para_cards().filter(produtor=produtor).order_by("data")
    )
    passados = (
        Evento.objects.publicados().para_cards()
        .filter(produtor=produtor)
        .filter(Q(data_fim__lt=agora) | Q(data_fim__isnull=True, data__lt=agora))
        .order_by("-data")[:6]
    )
    return render(request, "eventos/produtor-detalhe.html", {
        "produtor": produtor,
        "pagina": paginar(request, proximos, EVENTOS_POR_PAGINA),
        "total": proximos.count(),
        "passados": passados,
        "favoritos_do_usuario": ids_favoritos(request.user),
        "canonica": request.build_absolute_uri(produtor.get_absolute_url()),
    })


# =========================
# INGRESSOS
# =========================

@login_required
@limitar("reserva", por_usuario=True)
def reservar_ingresso(request, slug):
    evento = get_object_or_404(Evento, slug=slug, status=Evento.Status.PUBLICADO)

    if evento.ja_aconteceu:
        messages.error(request, "Este evento já aconteceu.")
        return redirect(evento)

    ja_reservados = reservas.ingressos_do_usuario(evento, request.user)
    restantes_usuario = max(0, (evento.limite_por_usuario or 10) - ja_reservados)
    vagas = reservas.vagas_restantes(evento)
    maximo = min(restantes_usuario, vagas) if vagas is not None else restantes_usuario

    if request.method == "POST":
        try:
            reserva = reservas.reservar(
                request.user, evento, request.POST.get("tipo"), request.POST.get("quantidade", 1)
            )
        except reservas.ReservaInvalida as erro:
            messages.error(request, str(erro))
            return redirect("reservar_ingresso", slug=evento.slug)

        from . import emails

        emails.reserva_confirmada(
            reserva, request.build_absolute_uri(evento.get_absolute_url())
        )
        plural = "s" if reserva.quantidade > 1 else ""
        messages.success(
            request,
            f"{reserva.quantidade} ingresso{plural} reservado{plural} para {evento.nome}.",
        )
        return redirect("meus_ingressos")

    tipo_inicial = request.GET.get("tipo")
    return render(request, "eventos/reservar-ingresso.html", {
        "evento": evento,
        "valor_inteira": evento.valor_para(Ingresso.Tipo.INTEIRA),
        "valor_meia": evento.valor_para(Ingresso.Tipo.MEIA),
        "tipo_selecionado": tipo_inicial if tipo_inicial in Ingresso.Tipo.values else Ingresso.Tipo.INTEIRA,
        "preco_definido": evento.gratuito or evento.preco is not None,
        "maximo": maximo,
        "ja_reservados": ja_reservados,
        "vagas": vagas,
        "esgotado": evento.esgotado,
    })


@login_required
def meus_ingressos(request):
    agora = timezone.now()
    base = (
        Ingresso.objects.filter(usuario=request.user)
        .select_related("evento", "evento__local_ref")
    )
    # A separação passou a ser feita no banco: antes, todos os ingressos do
    # usuário eram carregados na memória e ordenados em Python.
    futuro = Q(evento__data_fim__gte=agora) | Q(evento__data_fim__isnull=True, evento__data__gte=agora)
    proximos = base.exclude(status=Ingresso.Status.CANCELADO).filter(futuro).order_by("evento__data")
    passados = base.exclude(status=Ingresso.Status.CANCELADO).exclude(futuro).order_by("-evento__data")
    cancelados = base.filter(status=Ingresso.Status.CANCELADO).order_by("-cancelado_em", "-data_compra")

    return render(request, "eventos/meus-ingressos.html", {
        "proximos": proximos[:INGRESSOS_POR_PAGINA * 2],
        "passados": passados[:INGRESSOS_POR_PAGINA],
        "cancelados": cancelados[:INGRESSOS_POR_PAGINA],
        "total_proximos": proximos.count(),
        "total_passados": passados.count(),
        "total_cancelados": cancelados.count(),
    })


@login_required
@require_POST
def cancelar_ingresso(request, codigo):
    ingresso = get_object_or_404(
        Ingresso.objects.select_related("evento"), codigo=codigo, usuario=request.user
    )
    try:
        reservas.cancelar(ingresso)
    except reservas.ReservaInvalida as erro:
        messages.error(request, str(erro))
    else:
        from . import emails

        emails.reserva_cancelada(
            ingresso, request.build_absolute_uri(ingresso.evento.get_absolute_url())
        )
        messages.success(request, f"Ingresso para {ingresso.evento.nome} cancelado.")
    return redirect("meus_ingressos")


@login_required
def validar_ingresso(request, codigo):
    ingresso = get_object_or_404(
        Ingresso.objects.select_related("evento", "usuario"), codigo=codigo
    )
    evento = ingresso.evento
    autorizado = request.user.is_staff or evento.criado_por_id == request.user.id
    if not autorizado:
        raise Http404("Ingresso não encontrado.")

    if request.method == "POST":
        try:
            reservas.marcar_utilizado(ingresso)
        except reservas.ReservaInvalida as erro:
            messages.error(request, str(erro))
        else:
            messages.success(request, f"Entrada liberada para {ingresso.usuario.get_full_name() or ingresso.usuario.email}.")
        return redirect("validar_ingresso", codigo=codigo)

    return render(request, "eventos/validar-ingresso.html", {"ingresso": ingresso, "evento": evento})


# =========================
# FAVORITOS
# =========================

def ids_favoritos(usuario):
    if not usuario.is_authenticated:
        return set()
    return set(Favorito.objects.filter(usuario=usuario).values_list("evento_id", flat=True))


@login_required
@require_POST
@limitar("favorito", por_usuario=True)
def alternar_favorito(request, slug):
    evento = get_object_or_404(Evento, slug=slug, status=Evento.Status.PUBLICADO)
    favorito, criado = Favorito.objects.get_or_create(usuario=request.user, evento=evento)
    if not criado:
        favorito.delete()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"favorito": criado})

    messages.success(
        request,
        f"{evento.nome} salvo nos seus favoritos." if criado
        else f"{evento.nome} removido dos favoritos.",
    )
    return redirect(destino_seguro(request, evento.get_absolute_url()))


@login_required
def meus_favoritos(request):
    favoritos = (
        Favorito.objects.filter(usuario=request.user)
        .select_related("evento", "evento__local_ref", "evento__produtor")
        .order_by("evento__data")
    )
    pagina = paginar(request, favoritos, EVENTOS_POR_PAGINA)
    return render(request, "eventos/meus-favoritos.html", {
        "pagina": pagina,
        "eventos": [f.evento for f in pagina.object_list],
        "total": pagina.paginator.count,
        "favoritos_do_usuario": ids_favoritos(request.user),
    })


# =========================
# EVENTOS DO USUÁRIO
# =========================

@login_required
@limitar("criar_evento", por_usuario=True)
def criar_evento(request):
    formulario = EventoPublicoForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        evento, _ = catalogo.salvar_evento_do_produtor(
            formulario.save(commit=False), request.user
        )
        gerar_variantes_de_capa(evento)
        from . import emails

        emails.evento_recebido(evento, request.build_absolute_uri(evento.get_absolute_url()))
        messages.success(
            request,
            f"{evento.nome} foi enviado para aprovação. Avisaremos por e-mail assim que for publicado.",
        )
        return redirect("meus_eventos")

    return render(request, "eventos/editar-evento.html", {
        "form": formulario,
        "form_link": ColarLinkForm(),
        "titulo": "Cadastrar evento",
        "acao": "Enviar para aprovação",
        "locais_conhecidos": Local.objects.order_by("nome").values_list("nome", flat=True)[:400],
    })


@login_required
@limitar("colar_link", por_usuario=True)
def colar_link(request):
    formulario_link = ColarLinkForm(request.POST or None)
    dados_iniciais, aviso = {}, ""

    if request.method == "POST" and formulario_link.is_valid():
        from .ingestao import jsonld

        previa = jsonld.previa_de_link(formulario_link.cleaned_data["url"])
        if previa.get("erro"):
            messages.error(request, previa["erro"])
        else:
            dados_iniciais = {
                "nome": previa.get("nome", ""),
                "descricao": previa.get("descricao", ""),
                "local": previa.get("local", ""),
                "endereco": previa.get("endereco", ""),
                "organizador": previa.get("organizador", ""),
                "preco": previa.get("preco"),
                "gratuito": previa.get("gratuito", False),
                "data": previa.get("data"),
                "data_fim": previa.get("data_fim"),
            }
            aviso = f"Preenchido a partir de {previa.get('origem', 'link')}. Confira antes de enviar."

    formulario = EventoPublicoForm(
        initial={k: v for k, v in dados_iniciais.items() if v not in (None, "")}
    )
    return render(request, "eventos/editar-evento.html", {
        "form": formulario,
        "form_link": formulario_link,
        "aviso_previa": aviso,
        "titulo": "Cadastrar evento",
        "acao": "Enviar para aprovação",
        "locais_conhecidos": Local.objects.order_by("nome").values_list("nome", flat=True)[:400],
    })


@login_required
def editar_evento(request, slug):
    evento = get_object_or_404(Evento, slug=slug, criado_por=request.user)
    # Cópia do estado anterior para saber o que mudou.
    original = Evento.objects.get(pk=evento.pk)
    formulario = EventoForm(request.POST or None, request.FILES or None, instance=evento)

    if request.method == "POST" and formulario.is_valid():
        evento, voltaram = catalogo.salvar_evento_do_produtor(
            formulario.save(commit=False), request.user, original=original
        )
        gerar_variantes_de_capa(evento)
        if voltaram:
            from . import emails

            emails.evento_voltou_para_revisao(
                evento,
                [ROTULO_CAMPO.get(campo, campo) for campo in voltaram],
                request.build_absolute_uri(evento.get_absolute_url()),
            )
            messages.warning(
                request,
                f"{evento.nome} foi atualizado e voltou para revisão, porque "
                f"{listar_campos(voltaram)} mudou. Avisamos assim que for republicado.",
            )
        else:
            messages.success(request, f"{evento.nome} foi atualizado.")
        return redirect("meus_eventos")

    return render(request, "eventos/editar-evento.html", {
        "form": formulario,
        "evento": evento,
        "titulo": "Editar evento",
        "acao": "Salvar alterações",
        "locais_conhecidos": Local.objects.order_by("nome").values_list("nome", flat=True)[:400],
    })


ROTULO_CAMPO = {
    "nome": "o nome", "data": "a data", "data_fim": "o término", "local": "o local",
    "local_ref": "o local", "endereco": "o endereço", "regiao": "a região",
    "cidade": "a cidade", "modalidade": "o formato", "preco": "o preço",
    "gratuito": "a gratuidade", "link_ingressos": "o link de ingressos",
    "organizador": "o organizador",
}


def listar_campos(campos):
    nomes = []
    for campo in campos:
        rotulo = ROTULO_CAMPO.get(campo, campo)
        if rotulo not in nomes:
            nomes.append(rotulo)
    if len(nomes) == 1:
        return nomes[0]
    return ", ".join(nomes[:-1]) + f" e {nomes[-1]}"


def gerar_variantes_de_capa(evento):
    from .services import imagens

    for campo, rotulo in (("imagem", "capa"), ("banner", "banner")):
        arquivo = getattr(evento, campo)
        if not arquivo:
            continue
        try:
            imagens.gerar_variantes(arquivo)
        except Exception as erro:
            logger.warning("Variantes do(a) %s de %s falharam: %s", rotulo, evento.pk, erro)


@login_required
def meus_eventos(request):
    eventos = (
        Evento.objects.filter(criado_por=request.user)
        .select_related("local_ref", "produtor")
        .annotate(
            total_ingressos=Count(
                "ingressos", filter=~Q(ingressos__status=Ingresso.Status.CANCELADO)
            )
        )
        .order_by("-criado_em", "-id")
    )
    return render(request, "eventos/meus-eventos.html", {
        "eventos": eventos,
        "produtor": Produtor.objects.filter(user=request.user).first(),
    })


@login_required
def solicitar_destaque(request, slug):
    evento = get_object_or_404(Evento, slug=slug, criado_por=request.user)
    ja_tem_pedido = evento.solicitacoes_destaque.filter(atendida=False).exists()

    if request.method == "POST" and not ja_tem_pedido:
        formulario = SolicitacaoDestaqueForm(request.POST)
        if formulario.is_valid():
            solicitacao = formulario.save(commit=False)
            solicitacao.evento = evento
            solicitacao.save()
            messages.success(
                request,
                "Pedido enviado. A equipe confirma o pagamento e ativa o destaque em seguida.",
            )
            return redirect("meus_eventos")
    else:
        formulario = SolicitacaoDestaqueForm()

    planos = [
        {"valor": p.value, "nome": p.label, "preco": PRECO_POR_PLANO[p], "beneficio": BENEFICIOS_POR_PLANO[p]}
        for p in PlanoDestaque
        if p != PlanoDestaque.NORMAL
    ]
    return render(request, "eventos/solicitar-destaque.html", {
        "form": formulario,
        "evento": evento,
        "ja_tem_pedido": ja_tem_pedido,
        "planos": planos,
    })


@login_required
def inscritos_do_evento(request, slug):
    evento = get_object_or_404(Evento, slug=slug, criado_por=request.user)
    ingressos = (
        Ingresso.objects.filter(evento=evento)
        .exclude(status=Ingresso.Status.CANCELADO)
        .select_related("usuario")
        .order_by("data_compra")
    )
    if request.GET.get("formato") == "csv":
        return csv_de_inscritos(evento, ingressos)
    return render(request, "eventos/inscritos.html", {
        "evento": evento,
        "pagina": paginar(request, ingressos, 50),
        "total": ingressos.count(),
        "vagas": evento.vagas_disponiveis,
    })


CARACTERES_FORMULA_CSV = ("=", "+", "-", "@", "\t", "\r")


def campo_csv_seguro(valor):
    texto = str(valor)
    if texto.startswith(CARACTERES_FORMULA_CSV):
        return "'" + texto
    return texto


def csv_de_inscritos(evento, ingressos):
    import csv

    from django.utils.text import slugify

    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="inscritos-{slugify(evento.nome)[:40]}.csv"'
    )
    resposta.write("\ufeff")  # BOM: o Excel em pt-BR precisa disso
    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow(["codigo", "nome", "email", "tipo", "status", "valor", "reservado_em"])
    for ingresso in ingressos:
        escritor.writerow([
            ingresso.codigo_curto,
            campo_csv_seguro(ingresso.usuario.get_full_name() or ""),
            campo_csv_seguro(ingresso.usuario.email),
            ingresso.get_tipo_display(),
            ingresso.get_status_display(),
            f"{ingresso.valor:.2f}".replace(".", ","),
            timezone.localtime(ingresso.data_compra).strftime("%d/%m/%Y %H:%M"),
        ])
    return resposta


@login_required
def perfil_produtor(request):
    produtor = Produtor.objects.filter(user=request.user).first()
    formulario = ProdutorForm(request.POST or None, request.FILES or None, instance=produtor)
    if request.method == "POST" and formulario.is_valid():
        produtor = formulario.save(commit=False)
        produtor.user = request.user
        produtor.save()
        messages.success(request, "Perfil de produtor atualizado.")
        return redirect("meus_eventos")
    return render(request, "eventos/perfil-produtor.html", {
        "form": formulario,
        "produtor": produtor,
    })


# =========================
# CONTA
# =========================

def cadastro(request):
    if request.method == "POST" and excedeu("cadastro", request):
        return resposta_429(request, "Muitas contas criadas deste endereço. Tente mais tarde.")

    if request.user.is_authenticated:
        return redirect("home")

    formulario = CadastroForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        usuario = formulario.criar_usuario(ip=ip_do_pedido(request))
        if usuario is not None:
            autenticar(request, usuario)
            messages.success(request, f"Conta criada. Bem-vindo à {settings.SITE_NOME}.")
            return redirect("home")

    return render(request, "eventos/cadastro.html", {"form": formulario})


@login_required
def minha_privacidade(request):
    return render(request, "eventos/minha-privacidade.html", {
        "total_ingressos": request.user.ingressos.count(),
        "total_favoritos": request.user.favoritos.count(),
        "total_eventos": Evento.objects.filter(criado_por=request.user).count(),
        "aceites": request.user.aceites.all()[:5],
    })


@login_required
def exportar_meus_dados(request):
    dados = lgpd.exportar_dados(request.user)
    resposta = HttpResponse(
        json.dumps(dados, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    hoje = timezone.localdate().isoformat()
    resposta["Content-Disposition"] = f'attachment; filename="finde-meus-dados-{hoje}.json"'
    return resposta


@login_required
def excluir_minha_conta(request):
    if request.method == "POST" and excedeu("excluir_conta", request, por_usuario=True):
        return resposta_429(request)

    formulario = ExclusaoDeContaForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and formulario.is_valid():
        from . import emails

        email = request.user.email
        resumo = lgpd.excluir_conta(request.user)
        encerrar_sessao(request)
        emails.conta_excluida(email, resumo)
        messages.success(
            request,
            "Sua conta foi excluída. Ingressos e favoritos foram apagados; "
            "os eventos que você publicou continuam no ar, sem vínculo com você.",
        )
        return redirect("home")

    return render(request, "eventos/excluir-conta.html", {
        "form": formulario,
        "total_ingressos": request.user.ingressos.count(),
        "total_favoritos": request.user.favoritos.count(),
        "total_eventos": Evento.objects.filter(criado_por=request.user).count(),
    })


# =========================
# PÁGINAS INSTITUCIONAIS
# =========================

def pagina_offline(request):
    # Precacheada pelo service worker (sw.js) para aparecer quando a rede
    # cair no meio da navegação. Fora desse cenário é só mais uma página.
    return render(request, "eventos/offline.html")


def pagina_ajuda(request):
    return render(request, "eventos/ajuda.html", {
        "email_contato": settings.EMAIL_CONTATO,
        "email_lgpd": settings.EMAIL_ENCARREGADO_LGPD,
    })


def pagina_contato(request):
    return render(request, "eventos/contato.html", {
        "email_contato": settings.EMAIL_CONTATO,
        "email_lgpd": settings.EMAIL_ENCARREGADO_LGPD,
    })


def pagina_termos(request):
    from .services.lgpd import VERSAO_TERMOS

    return render(request, "eventos/termos.html", {
        "atualizado_em": "16 de setembro de 2026",
        "versao": VERSAO_TERMOS,
        "razao_social": settings.RAZAO_SOCIAL,
        "cnpj": settings.CNPJ,
        "endereco_comercial": settings.ENDERECO_COMERCIAL,
    })


def pagina_privacidade(request):
    from .services.lgpd import VERSAO_PRIVACIDADE

    return render(request, "eventos/privacidade.html", {
        "atualizado_em": "16 de setembro de 2026",
        "versao": VERSAO_PRIVACIDADE,
        "email_lgpd": settings.EMAIL_ENCARREGADO_LGPD,
    })


def pagina_cookies(request):
    return render(request, "eventos/cookies.html", {
        "atualizado_em": "16 de setembro de 2026",
    })


def pagina_acessibilidade(request):
    return render(request, "eventos/acessibilidade.html", {
        "atualizado_em": "16 de setembro de 2026",
    })


def pagina_anuncie(request):
    planos = [
        {"valor": p.value, "nome": p.label, "preco": PRECO_POR_PLANO[p], "beneficio": BENEFICIOS_POR_PLANO[p]}
        for p in PlanoDestaque
        if p != PlanoDestaque.NORMAL
    ]
    return render(request, "eventos/anuncie.html", {"planos": planos})


def pagina_reembolso(request):
    return render(request, "eventos/reembolso.html", {
        "atualizado_em": "16 de setembro de 2026",
        "email_contato": settings.EMAIL_CONTATO,
    })


def pagina_sobre(request):
    return render(request, "eventos/sobre.html", {
        "total_eventos": Evento.objects.visiveis().count(),
        "total_locais": Local.objects.filter(eventos__status=Evento.Status.PUBLICADO).distinct().count(),
        "total_produtores": Produtor.objects.filter(eventos__isnull=False).distinct().count(),
    })


def robots_txt(request):
    linhas = [
        "User-agent: *",
        "Allow: /",
        f"Disallow: /{settings.ADMIN_URL}/",
        "Disallow: /conta/",
        "Disallow: /meus-ingressos/",
        "Disallow: /meus-eventos/",
        "Disallow: /favoritos/",
        "Disallow: /ingresso/",
        "Disallow: /mapa/dados/",
        "Disallow: /saude/",
        "Disallow: /assistente/",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(linhas), content_type="text/plain")


# =========================
# ASSISTENTE DE IA
# =========================

@require_POST
@limitar("assistente", metodos=("POST",))
def assistente_perguntar(request):
    from .services import assistente

    try:
        dados = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "Corpo da requisição inválido."}, status=400)

    pergunta = str(dados.get("pergunta", "")).strip()[:500]
    if not pergunta:
        return JsonResponse({"erro": "Digite uma pergunta."}, status=400)

    historico = dados.get("historico") or []
    historico_seguro = [
        {"role": item.get("role"), "content": str(item.get("content", ""))[:500]}
        for item in historico[-6:]
        if isinstance(item, dict) and item.get("role") in ("user", "assistant")
    ]

    try:
        resposta = assistente.responder(pergunta, historico=historico_seguro)
    except assistente.AssistenteIndisponivel:
        return JsonResponse(
            {"erro": "O assistente está indisponível no momento. Tente de novo mais tarde."},
            status=503,
        )
    return JsonResponse({"resposta": resposta})


# =========================
# OBSERVABILIDADE
# =========================

def health_check(request):
    return JsonResponse({"status": "ok", "servico": settings.SITE_NOME})


def health_check_detalhado(request):
    token = getattr(settings, "HEALTHCHECK_TOKEN", "")
    if not token or not secrets.compare_digest(request.GET.get("token", ""), token):
        raise Http404

    resultado = {"aplicacao": "ok"}
    estado_geral = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        resultado["banco"] = "ok"
    except Exception as erro:
        resultado["banco"] = f"erro: {erro}"
        estado_geral = 503

    try:
        from django.core.cache import cache

        cache.set("saude", "1", 10)
        resultado["cache"] = "ok" if cache.get("saude") == "1" else "erro: leitura falhou"
        if resultado["cache"] != "ok":
            estado_geral = 503
    except Exception as erro:
        resultado["cache"] = f"erro: {erro}"
        estado_geral = 503

    try:
        from django.core.files.storage import default_storage

        default_storage.exists("saude-check")
        resultado["storage"] = "ok"
    except Exception as erro:
        resultado["storage"] = f"erro: {erro}"
        estado_geral = 503

    try:
        resultado["eventos_publicados"] = Evento.objects.visiveis().count()
        resultado["locais_sem_coordenada"] = Local.objects.pendentes_de_geocodificacao().count()
    except Exception:
        pass

    return JsonResponse(resultado, status=estado_geral)


# =========================
# UTILITÁRIOS
# =========================

def destino_seguro(request, padrao):
    destino = request.POST.get("proximo") or ""
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return padrao


def paginar(request, queryset, por_pagina):
    paginator = Paginator(queryset, por_pagina)
    return paginator.get_page(request.GET.get("page"))


def erro_403(request, exception=None):
    return render(request, "403.html", status=403)


def erro_404(request, exception=None):
    return render(request, "404.html", status=404)


def erro_500(request):
    # Sem contexto de banco: um 500 costuma ser justamente o banco caindo.
    from django.template import loader

    return HttpResponse(loader.get_template("500.html").render({}), status=500)
