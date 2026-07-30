"""Fixtures compartilhadas de toda a suíte.

Arquitetura em camadas: os testes (checks/) só conhecem estas fixtures;
todo o detalhe de HTTP/navegador vive em webqa/ — baixo acoplamento e
testabilidade da própria suíte (verificação em tests/).
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from webqa import metricas
from webqa.config import Settings, load_settings
from webqa.http_utils import Timing, make_client, timed_get
from webqa.trackers import LoggedRequest, NetworkLog


@pytest.fixture(scope="session")
def settings() -> Settings:
    cfg = load_settings()
    if not cfg.target_url:
        pytest.exit("Defina target_url em config.yaml ou WEBQA_TARGET_URL.")
    return cfg


@pytest.fixture(scope="session")
def client(settings):
    with make_client(settings) as c:
        yield c


@pytest.fixture(scope="session")
def home_response(client, settings):
    """Resposta da página inicial — reutilizada por dezenas de testes
    para não martelar o alvo (respeito ao sistema sob teste)."""
    resp = client.get(settings.target_url)
    resp.raise_for_status()
    return resp


@pytest.fixture(scope="session")
def home_timing(client, settings) -> Timing:
    """Latência da home, medida UMA vez e registrada para o consolidado.

    O registro fica na fixture, não nos testes: assim a medida existe mesmo que
    o teste de orçamento passe — e ninguém precisa lembrar de registrar ao
    escrever o próximo teste que consome esta fixture."""
    medida = timed_get(client, settings.target_url)
    metricas.registrar("ttfb_ms", medida.ttfb_ms)
    metricas.registrar("total_ms", medida.total_ms)
    return medida


@pytest.fixture(scope="session")
def soup(home_response) -> BeautifulSoup:
    return BeautifulSoup(home_response.text, "lxml")


# ---------- Navegador (Playwright) ----------

@pytest.fixture(scope="session")
def browser(settings):
    """Instância única de Chromium por sessão (contextos é que são isolados).
    Se o Playwright/Chromium não estiver instalado, os testes 'browser'
    são pulados com instrução clara (falha explicada > falha misteriosa)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")

    with sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except Exception as exc:  # navegador ausente
            pytest.skip(f"Chromium indisponível: rode `python -m playwright install chromium` ({exc}).")
        yield instance
        instance.close()


@pytest.fixture(scope="session")
def browser_page(browser):
    """Página Chromium real para medir renderização e acessibilidade."""
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture(scope="module")
def network_log(browser, settings) -> NetworkLog:
    """Carrega o alvo em contexto NOVO E VIRGEM e devolve o que a rede revelou.

    Contrato (webqa/trackers.py::NetworkLog): `.requests` (url, resource_type de
    TODA requisição, inclusive as de terceiros) e `.cookies` (cookies do contexto
    após o load).

    Contexto próprio, não a página da sessão: cookie ou consentimento herdado de
    um teste anterior faria o alvo parecer conforme ("já consentiu antes") —
    o pior falso negativo possível numa bateria de consentimento prévio.
    """
    context = browser.new_context(user_agent=settings.user_agent)
    requests: list[LoggedRequest] = []
    context.on("request", lambda r: requests.append(LoggedRequest(r.url, r.resource_type)))
    page = context.new_page()
    try:
        page.goto(settings.target_url, wait_until="load", timeout=60_000)
        # Tags de analytics costumam disparar depois do load; observar cedo demais
        # produziria aprovação falsa.
        page.wait_for_timeout(2_000)
        yield NetworkLog(
            url=settings.target_url,
            requests=tuple(requests),
            cookies=tuple(context.cookies()),
        )
    finally:
        context.close()
