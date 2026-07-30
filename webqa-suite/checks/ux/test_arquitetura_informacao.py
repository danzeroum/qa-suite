"""Arquitetura de Informação: organização, navegação, rotulação e hierarquia."""
import re

import pytest

pytestmark = pytest.mark.ux


def test_hierarquia_h1_unico(soup):
    h1s = soup.find_all("h1")
    assert len(h1s) == 1, (
        f"{len(h1s)} elementos <h1> — a página precisa de exatamente um título principal."
    )


def test_hierarquia_sem_saltos_de_heading(soup):
    levels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    if len(levels) < 2:
        pytest.skip("Poucos headings para avaliar hierarquia.")
    saltos = [(a, b) for a, b in zip(levels, levels[1:], strict=False) if b - a > 1]
    assert not saltos, (
        f"Saltos na hierarquia de headings {saltos} (ex.: h2→h4) — quebra o contorno lógico do conteúdo."
    )


def test_navegacao_principal_existe(soup):
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    assert nav is not None, "Sem <nav>/role=navigation — navegação principal não identificável."


def test_rotulacao_navegacao_com_texto(soup):
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    if nav is None:
        pytest.skip("Sem nav.")
    links = [a.get_text(strip=True) or a.get("aria-label", "") for a in nav.find_all("a")]
    vazios = [lk for lk in links if not lk]
    assert not vazios, f"{len(vazios)} itens de navegação sem rótulo (nem aria-label)."


def test_organizacao_sitemap_ou_robots(client, settings):
    """Encontrabilidade: sitemap.xml/robots.txt ajudam usuários (via busca) e crawlers."""
    ok = False
    for path in ("/sitemap.xml", "/robots.txt"):
        try:
            if client.get(settings.target_url + path).status_code == 200:
                ok = True
        except Exception:
            pass
    if not ok:
        pytest.xfail("Sem sitemap.xml nem robots.txt — encontrabilidade reduzida.")


def test_profundidade_conteudo_principal(soup):
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    if main is None:
        pytest.xfail("Sem <main>/role=main — leitores de tela não localizam o conteúdo principal.")
