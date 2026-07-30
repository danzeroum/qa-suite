"""Fixtures compartilhadas de toda a suíte.

Arquitetura em camadas: os testes (checks/) só conhecem estas fixtures;
todo o detalhe de HTTP/navegador vive em webqa/ — baixo acoplamento e
testabilidade da própria suíte (verificação em tests/).
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from webqa.config import Settings, load_settings
from webqa.http_utils import Timing, make_client, timed_get


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
    return timed_get(client, settings.target_url)


@pytest.fixture(scope="session")
def soup(home_response) -> BeautifulSoup:
    return BeautifulSoup(home_response.text, "lxml")


# ---------- Navegador (Playwright) ----------

@pytest.fixture(scope="session")
def browser_page(settings):
    """Página Chromium real para medir renderização e acessibilidade.
    Se o Playwright/Chromium não estiver instalado, os testes 'browser'
    são pulados com instrução clara (falha explicada > falha misteriosa)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # navegador ausente
            pytest.skip(f"Chromium indisponível: rode `python -m playwright install chromium` ({exc}).")
        page = browser.new_page()
        yield page
        browser.close()
