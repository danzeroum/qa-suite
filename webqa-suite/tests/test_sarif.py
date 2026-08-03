"""VERIFICAÇÃO da exportação SARIF (C2 fatia 2). Sem rede: puro sobre Finding."""
from __future__ import annotations

import json

import pytest

from webqa.dominio import Finding
from webqa.sarif import para_sarif, serializar_sarif

pytestmark = pytest.mark.verification


def _finding(sev="alta", tipo="exposicao:vcs"):
    return Finding(tipo, "https://a/.git/HEAD", sev, "presente", "C",
                   remediacao="Bloqueie /.git.", procedencia="OWASP WSTG-CONF-004")


def test_sarif_tem_estrutura_2_1_0():
    doc = para_sarif([_finding()])
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "WebQA-FaseC"
    assert len(doc["runs"][0]["results"]) == 1


def test_sarif_mapeia_severidade_para_nivel():
    niveis = {para_sarif([_finding(sev=s)])["runs"][0]["results"][0]["level"]
              for s in ("alta", "media", "baixa")}
    # alta→error (reprova CI/aba Security), media→warning, baixa→note
    r_alta = para_sarif([_finding(sev="alta")])["runs"][0]["results"][0]["level"]
    r_media = para_sarif([_finding(sev="media")])["runs"][0]["results"][0]["level"]
    r_baixa = para_sarif([_finding(sev="baixa")])["runs"][0]["results"][0]["level"]
    assert (r_alta, r_media, r_baixa) == ("error", "warning", "note")
    assert niveis == {"error", "warning", "note"}


def test_sarif_result_carrega_recurso_e_procedencia():
    res = para_sarif([_finding()])["runs"][0]["results"][0]
    assert res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "https://a/.git/HEAD"
    assert res["properties"]["procedencia"] == "OWASP WSTG-CONF-004"
    assert res["properties"]["remediacao"] == "Bloqueie /.git."


def test_sarif_so_usa_campos_mascarados_do_finding():
    """SARIF não pode reintroduzir segredo: o Finding mascara no construtor, e o
    SARIF só lê campos do Finding. Um segredo na evidência sai mascarado."""
    f = Finding("exposicao:configuracao", "https://a/.env", "alta",
                "AKIAIOSFODNN7EXAMPLE vazou", "C", remediacao="Bloqueie.",
                procedencia="CWE-538")
    texto = serializar_sarif([f])
    assert "AKIAIOSFODNN7EXAMPLE" not in texto      # mascarado pelo Finding
    assert json.loads(texto)["version"] == "2.1.0"  # e é JSON válido


def test_sarif_vazio_e_valido():
    doc = para_sarif([])
    assert doc["runs"][0]["results"] == []
    assert doc["runs"][0]["tool"]["driver"]["rules"] == []
