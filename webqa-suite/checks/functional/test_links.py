"""Crawler funcional: links internos não podem estar quebrados (nível: sistema).

Limitado por config (crawl.max_pages) para respeitar o alvo — teste é
diagnóstico, não ataque.
"""
from urllib.parse import urljoin, urlparse

import pytest

from webqa.sanitize import safe_url

pytestmark = pytest.mark.functional


def _internal_links(soup, base, host):
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base + "/", href).split("#")[0]
        if urlparse(url).netloc == host:
            seen.add(url)
    return seen


def test_links_internos_sem_quebrados(client, soup, settings):
    host = urlparse(settings.target_url).netloc
    fila = list(_internal_links(soup, settings.target_url, host))[: settings.crawl_max_pages]
    quebrados = []
    for url in fila:
        try:
            resp = client.head(url)
            if resp.status_code >= 405:  # HEAD não suportado
                resp = client.get(url)
        except Exception as exc:
            quebrados.append((safe_url(url), f"erro: {type(exc).__name__}"))
            continue
        if resp.status_code >= 400:
            quebrados.append((safe_url(url), resp.status_code))
    assert not quebrados, (
        f"{len(quebrados)} links internos quebrados:\n"
        + "\n".join(f"  {u} -> {s}" for u, s in quebrados)
    )


def test_links_externos_declarados_com_seguranca(soup):
    """target=_blank sem rel=noopener é risco (tab-nabbing)."""
    problematicos = [
        a.get("href", "?")[:80]
        for a in soup.find_all("a", href=True)
        if a.get("target") == "_blank" and "noopener" not in " ".join(a.get("rel", []))
    ]
    assert not problematicos, (
        f"{len(problematicos)} links _blank sem rel=noopener: {problematicos[:5]}"
    )
