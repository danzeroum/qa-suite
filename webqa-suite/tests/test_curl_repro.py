"""VERIFICAÇÃO do curl reproduzível (C3c). Puro sobre Finding, sem rede."""
from __future__ import annotations

import pytest

from webqa.curl_repro import curl_de
from webqa.dominio import Finding

pytestmark = pytest.mark.verification


def _f(recurso, metodo="HEAD"):
    return Finding("exposicao:vcs", recurso, "alta", "presente", "C",
                   remediacao="corrija", metodo=metodo)


def test_curl_head_por_padrao_com_resolve():
    cmd = curl_de(_f("https://a.exemplo/.git/HEAD"), "203.0.113.7")
    assert " -I " in cmd
    assert "--resolve a.exemplo:443:203.0.113.7" in cmd
    assert cmd.endswith("https://a.exemplo/.git/HEAD")


def test_curl_usa_range_quando_metodo_foi_get_range():
    cmd = curl_de(_f("https://a.exemplo/.env", metodo="GET(range)"), "203.0.113.7")
    assert "-r 0-0" in cmd
    assert " -I " not in cmd


@pytest.mark.parametrize("metodo", ["HEAD", "GET(range)"])
def test_curl_ip_nunca_na_url_so_no_resolve(metodo):
    """Nos DOIS ramos (HEAD e GET Range): o IP só no --resolve, nunca na URL."""
    cmd = curl_de(_f("https://a.exemplo/.git/HEAD", metodo=metodo), "203.0.113.7")
    assert "https://203.0.113.7" not in cmd            # IP jamais como host da URL
    assert "--resolve a.exemplo:443:203.0.113.7" in cmd
    assert cmd.endswith("https://a.exemplo/.git/HEAD")  # URL sempre a lógica


def test_curl_preserva_porta_nao_padrao_no_resolve():
    cmd = curl_de(_f("https://a.exemplo:8443/.git/HEAD"), "203.0.113.7")
    assert "--resolve a.exemplo:8443:203.0.113.7" in cmd


def test_curl_nunca_baixa_corpo():
    """Detectar, nunca explorar — também no comando de reprodução."""
    assert "-o /dev/null" in curl_de(_f("https://a.exemplo/.git/HEAD"), "203.0.113.7")
