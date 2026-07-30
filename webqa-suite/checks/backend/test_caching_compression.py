"""Eficiência de tráfego: compressão e política de cache.

Impacta diretamente performance percebida e custo — 'toda decisão tem seu
preço': cache agressivo economiza, mas exige estratégia de invalidação.
"""
import pytest

pytestmark = pytest.mark.backend


def test_resposta_comprimida(client, settings):
    resp = client.get(
        settings.target_url,
        headers={"Accept-Encoding": "gzip, deflate, br, zstd"},
    )
    encoding = resp.headers.get("content-encoding", "")
    assert any(e in encoding for e in ("gzip", "br", "zstd", "deflate")), (
        "HTML servido sem compressão — desperdício de banda e pior TTFB efetivo."
    )


def test_politica_de_cache_declarada(home_response):
    assert "cache-control" in home_response.headers, (
        "Sem Cache-Control — comportamento de cache fica indefinido em proxies e navegadores."
    )


def test_validadores_de_cache(home_response, client, settings):
    """ETag/Last-Modified permitem 304 e economizam tráfego."""
    etag = home_response.headers.get("etag")
    last_mod = home_response.headers.get("last-modified")
    if not (etag or last_mod):
        pytest.skip("Sem ETag/Last-Modified na home (comum em páginas dinâmicas) — avalie para assets.")
    headers = {"If-None-Match": etag} if etag else {"If-Modified-Since": last_mod}
    resp = client.get(settings.target_url, headers=headers)
    assert resp.status_code in (200, 304), f"Revalidação retornou {resp.status_code}"
