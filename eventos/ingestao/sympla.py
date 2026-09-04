import json
import logging
import re
import time
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils.dateparse import parse_datetime

from .base import EventoImportado, garantir_aware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IMPORTADOR LEGADO — EM DESLIGAMENTO
#
# Este é o único conector que raspa uma página com navegador. Ele continua aqui
# por uma razão só: desligar antes de as fontes novas terem volume deixaria o
# catálogo vazio, e catálogo vazio mata o produto mais rápido do que qualquer
# risco jurídico.
#
# Vem desligado por padrão (SYMPLA_SCRAPING_ATIVO=False). Para remover de vez,
# siga o roteiro do README, seção "Desligamento do Selenium".
#
# PRAZO DE REMOÇÃO: assim que o Mapa nas Nuvens + parceiros + produtores
# sustentarem o catálogo. Compare com: manage.py comparar_catalogo
# ---------------------------------------------------------------------------

URL_LISTAGEM = "https://www.sympla.com.br/eventos/brasilia-df"
PAUSA_LISTAGEM = 3
PAUSA_EVENTO = 2
MAX_ROLAGENS = 15


@contextmanager
def navegador(headless=True):
    """Chrome controlado por Selenium. As dependências são opcionais e só
    carregam quando a importação é realmente executada."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as erro:
        raise RuntimeError(
            "A importação precisa dos extras de scraping. "
            "Instale com: pip install -r requirements-scraping.txt"
        ) from erro

    opcoes = Options()
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--window-size=1920,1080")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    if headless:
        opcoes.add_argument("--headless=new")

    driver = webdriver.Chrome(options=opcoes)
    try:
        yield driver
    finally:
        driver.quit()


def coletar(limite=50, headless=True, **_):
    if not getattr(settings, "SYMPLA_SCRAPING_ATIVO", False):
        raise RuntimeError(
            "O importador por Selenium está desligado (SYMPLA_SCRAPING_ATIVO=False). "
            "Use as fontes de ingestão legítimas: mapa-df, parceiros, produtor, sympla-produtor."
        )

    from selenium.webdriver.common.by import By

    with navegador(headless) as driver:
        driver.get(URL_LISTAGEM)
        time.sleep(PAUSA_LISTAGEM)

        links = _rolar_e_coletar_links(driver, By)
        logger.info("%d links de evento encontrados", len(links))

        for indice, link in enumerate(links[:limite], start=1):
            logger.info("[%d/%d] %s", indice, min(len(links), limite), link)
            try:
                driver.get(link)
                time.sleep(PAUSA_EVENTO)
                evento = _extrair_evento(driver, By, link)
            except Exception:
                logger.exception("Falha ao ler %s", link)
                continue

            if evento:
                yield evento


def _rolar_e_coletar_links(driver, By):
    vistos, sem_novidade = set(), 0

    for _ in range(MAX_ROLAGENS):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(PAUSA_LISTAGEM)

        antes = len(vistos)
        for ancora in driver.find_elements(By.TAG_NAME, "a"):
            href = ancora.get_attribute("href") or ""
            if "/evento/" in href and "termos" not in href and "politicas" not in href:
                vistos.add(href.split("?")[0])

        sem_novidade = sem_novidade + 1 if len(vistos) == antes else 0
        if sem_novidade >= 3:
            break

    return sorted(vistos)


def _extrair_evento(driver, By, link):
    dados = _ler_json_ld(driver, By)
    if not dados:
        logger.warning("Sem dados estruturados em %s — evento ignorado", link)
        return None

    inicio = _ler_data(dados.get("startDate"))
    if not inicio:
        logger.warning("Sem data de início em %s — evento ignorado", link)
        return None

    local, endereco = _ler_local(dados.get("location"))
    preco, gratuito = _ler_oferta(dados.get("offers"))

    return EventoImportado(
        id_externo=_extrair_identificador(link),
        nome=(dados.get("name") or "").strip(),
        data=inicio,
        data_fim=_ler_data(dados.get("endDate")),
        local=local,
        endereco=endereco,
        descricao=(dados.get("description") or "").strip()[:4000],
        organizador=_ler_organizador(dados.get("organizer")),
        imagem_url=_ler_imagem(dados.get("image")),
        link_original=link,
        preco=preco,
        gratuito=gratuito,
    )


def _ler_json_ld(driver, By):
    """Sympla publica schema.org/Event na página. É a fonte confiável de data e local —
    muito mais estável do que adivinhar por seletores de CSS."""
    for bloco in driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]'):
        conteudo = bloco.get_attribute("textContent") or ""
        try:
            dados = json.loads(conteudo)
        except json.JSONDecodeError:
            continue

        for item in dados if isinstance(dados, list) else [dados]:
            if isinstance(item, dict) and "Event" in str(item.get("@type", "")):
                return item
    return None


def _ler_data(valor):
    if not valor:
        return None
    analisada = parse_datetime(valor)
    if analisada:
        return garantir_aware(analisada)
    # Sem fuso na string, o datetime seria interpretado como UTC e o horário
    # sairia 3 horas atrasado. garantir_aware() ancora no fuso do projeto.
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return garantir_aware(datetime.strptime(valor, formato))
        except ValueError:
            continue
    return None


def _ler_local(location):
    if not isinstance(location, dict):
        return "", ""

    nome = (location.get("name") or "").strip()
    endereco = location.get("address")

    if isinstance(endereco, dict):
        partes = [
            endereco.get("streetAddress"),
            endereco.get("addressLocality"),
            endereco.get("addressRegion"),
        ]
        return nome, ", ".join(p.strip() for p in partes if p)
    if isinstance(endereco, str):
        return nome, endereco.strip()
    return nome, ""


def _ler_oferta(offers):
    if not offers:
        return None, False

    lista = offers if isinstance(offers, list) else [offers]
    valores = []
    for oferta in lista:
        if not isinstance(oferta, dict):
            continue
        bruto = oferta.get("price", oferta.get("lowPrice"))
        if bruto in (None, ""):
            continue
        try:
            valores.append(Decimal(str(bruto).replace(",", ".")))
        except InvalidOperation:
            continue

    if not valores:
        return None, False

    menor = min(valores)
    return (None, True) if menor == 0 else (menor, False)


def _ler_organizador(organizer):
    if isinstance(organizer, dict):
        return (organizer.get("name") or "").strip()
    if isinstance(organizer, str):
        return organizer.strip()
    return ""


def _ler_imagem(image):
    if isinstance(image, list):
        return next((i for i in image if isinstance(i, str)), "")
    if isinstance(image, dict):
        return image.get("url", "")
    return image if isinstance(image, str) else ""


def _extrair_identificador(link):
    encontrado = re.search(r"/evento/[^/]*?__?(\d+)/?$", link) or re.search(r"(\d{5,})", link)
    return encontrado.group(1) if encontrado else link.rstrip("/").rsplit("/", 1)[-1][:120]
