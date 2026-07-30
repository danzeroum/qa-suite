"""Qualidade estrutural do HTML (nível: integração de frontend).

Base para SEO, acessibilidade e renderização previsível.
"""
import pytest

pytestmark = pytest.mark.frontend


def test_doctype_html5(home_response):
    assert home_response.text.lstrip()[:15].lower().startswith("<!doctype html"), (
        "Sem <!doctype html> — navegador entra em quirks mode (renderização imprevisível)."
    )


def test_lang_declarado(soup):
    html = soup.find("html")
    assert html is not None and html.get("lang"), (
        "<html> sem atributo lang — quebra leitores de tela e tradução automática."
    )


def test_charset_utf8(soup, home_response):
    meta = soup.find("meta", charset=True)
    declared = meta["charset"].lower() if meta else ""
    if not declared:
        http_equiv = soup.find("meta", attrs={"http-equiv": lambda v: v and v.lower() == "content-type"})
        if http_equiv:
            declared = http_equiv.get("content", "").lower()
    if not declared:
        declared = home_response.headers.get("content-type", "").lower()
    assert "utf-8" in declared, (
        "Charset UTF-8 não declarado (nem <meta charset>, nem http-equiv, nem header) — "
        "risco de caracteres corrompidos."
    )


def test_title_presente_e_significativo(soup):
    title = soup.find("title")
    assert title and len(title.get_text(strip=True)) >= 5, (
        "<title> ausente ou curto demais — prejudica orientação do usuário e SEO."
    )


def test_meta_viewport_responsivo(soup):
    meta = soup.find("meta", attrs={"name": "viewport"})
    assert meta and "width=device-width" in meta.get("content", ""), (
        "Sem meta viewport — página não é responsiva em dispositivos móveis."
    )


def test_meta_description(soup):
    meta = soup.find("meta", attrs={"name": "description"})
    if not (meta and meta.get("content", "").strip()):
        pytest.xfail("Sem meta description — impacta SEO e prévia em buscadores.")


def test_tamanho_do_html_dentro_do_orcamento(home_response, settings):
    kb = len(home_response.content) / 1024
    limit = settings.threshold("html_kb")
    assert kb <= limit, (
        f"HTML com {kb:.0f}KB (> {limit:.0f}KB) — HTML gigante atrasa o parse e o FCP."
    )


def test_uso_de_html_semantico(soup):
    semantic = ("main", "nav", "header", "footer", "article", "section")
    found = [t for t in semantic if soup.find(t)]
    assert len(found) >= 2, (
        f"Pouco HTML semântico (encontrado: {found or 'nenhum'}) — "
        "dificulta acessibilidade e manutenção."
    )
