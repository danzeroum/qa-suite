"""CSS/JS/imagens: quantidade, minificação e recursos que bloqueiam renderização.

Orçamentos vêm de config.yaml — trade-off explícito entre riqueza da página
e velocidade de renderização.
"""
from urllib.parse import urljoin

import pytest

pytestmark = pytest.mark.frontend


def _stylesheets(soup):
    return [ln for ln in soup.find_all("link", rel=lambda r: r and "stylesheet" in r) if ln.get("href")]


def _scripts(soup):
    return soup.find_all("script", src=True)


def test_quantidade_de_css(soup, settings):
    n = len(_stylesheets(soup))
    assert n <= settings.threshold("css_files_max"), (
        f"{n} arquivos CSS — considere bundling/critical CSS."
    )


def test_quantidade_de_js(soup, settings):
    n = len(_scripts(soup))
    assert n <= settings.threshold("js_files_max"), (
        f"{n} arquivos JS externos — excesso de round-trips atrasa a interatividade."
    )


def test_scripts_bloqueantes_no_head(soup, settings):
    head = soup.find("head")
    if head is None:
        pytest.skip("Sem <head> identificável.")
    blocking = [
        s.get("src") for s in head.find_all("script", src=True)
        if not (s.has_attr("async") or s.has_attr("defer") or s.get("type") == "module")
    ]
    limit = settings.threshold("blocking_scripts_max")
    assert len(blocking) <= limit, (
        f"{len(blocking)} scripts bloqueantes no <head> (> {limit:.0f}): {blocking} — "
        "use defer/async para não travar a renderização."
    )


def test_js_principal_minificado(client, soup, settings):
    scripts = _scripts(soup)
    if not scripts:
        pytest.skip("Página sem JS externo.")
    url = urljoin(settings.target_url + "/", scripts[0]["src"])
    resp = client.get(url)
    if resp.status_code != 200 or not resp.text:
        pytest.skip(f"Não foi possível baixar {url}.")
    lines = resp.text.splitlines() or [""]
    avg_len = len(resp.text) / max(len(lines), 1)
    assert avg_len > 100 or len(resp.text) < 4096, (
        f"JS {url} parece não minificado (média de {avg_len:.0f} chars/linha) — "
        "bytes desnecessários no caminho crítico."
    )


def test_imagens_com_dimensoes_ou_lazy(soup):
    imgs = soup.find_all("img")
    if not imgs:
        pytest.skip("Página sem <img>.")
    sem_dim = [i.get("src", "?") for i in imgs if not (i.get("width") and i.get("height"))]
    proporcao = len(sem_dim) / len(imgs)
    assert proporcao <= 0.5, (
        f"{len(sem_dim)}/{len(imgs)} imagens sem width/height — causa layout shift (CLS)."
    )
