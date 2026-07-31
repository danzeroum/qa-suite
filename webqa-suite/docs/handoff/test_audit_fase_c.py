"""VERIFICAÇÃO da auditoria da Fase C — irmã de test_vazamento_de_credencial.

Prova as três proteções da linha de auditoria com violação plantada: segredo
registrado não vaza, query-string de caminho sensível some, e caractere de
controle não injeta linha falsa. Sem rede, sem arquivo (exceto o teste de append).
"""
from __future__ import annotations

import json

import pytest

from webqa import sanitize
from webqa.audit import AuditLog

pytestmark = pytest.mark.verification


@pytest.fixture(autouse=True)
def registro_limpo():
    sanitize.esquecer_valores_sensiveis()
    yield
    sanitize.esquecer_valores_sensiveis()


def _log() -> AuditLog:
    return AuditLog(run_id="run-1", escopo_hash="deadbeef")


def test_segredo_registrado_nao_vaza_para_a_linha():
    sanitize.registrar_valor_sensivel("supersecreto123", "SEGREDO")
    linha = _log().registrar(
        url="https://alvo.exemplo.br/x", metodo="HEAD",
        alvo="supersecreto123", autorizacao_id="ok")
    assert "supersecreto123" not in json.dumps(linha)


def test_query_string_de_caminho_sensivel_e_suprimida():
    linha = _log().registrar(
        url="https://alvo.exemplo.br/.git/HEAD?token=abc123", metodo="HEAD",
        alvo="alvo", autorizacao_id="ok")
    assert linha["url"] == "https://alvo.exemplo.br/.git/HEAD"
    assert "abc123" not in linha["url"] and "?" not in linha["url"]


def test_caractere_de_controle_e_escapado():
    linha = _log().registrar(
        url="https://alvo.exemplo.br/x", metodo="HEAD",
        alvo="normal\ninjetado", autorizacao_id="ok")
    assert "\n" not in linha["alvo"] and "\\n" in linha["alvo"]


def test_campo_longo_e_truncado():
    linha = _log().registrar(
        url="https://alvo.exemplo.br/x", metodo="HEAD",
        alvo="a" * 2000, autorizacao_id="ok")
    assert len(linha["alvo"]) <= 500


def test_timestamp_e_timezone_aware():
    linha = _log().registrar(
        url="https://alvo.exemplo.br/x", metodo="HEAD", alvo="a", autorizacao_id="ok")
    assert linha["ts"].endswith("+00:00")


def test_append_only_em_arquivo(tmp_path):
    caminho = tmp_path / "audit" / "run.jsonl"
    log = AuditLog(run_id="r", escopo_hash="h", caminho=caminho)
    log.registrar(url="https://a.exemplo.br/1", metodo="HEAD", alvo="a", autorizacao_id="ok")
    log.registrar(url="https://a.exemplo.br/2", metodo="HEAD", alvo="a", autorizacao_id="ok")
    linhas = caminho.read_text(encoding="utf-8").strip().splitlines()
    assert len(linhas) == 2
    for linha in linhas:
        json.loads(linha)  # cada linha é JSON válido e independente
