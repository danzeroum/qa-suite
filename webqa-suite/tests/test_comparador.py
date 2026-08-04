"""VERIFICAÇÃO do comparador entre laudos (frente E, E5).

O guarda da honestidade: só compara sob régua comum, e recusa NOMEANDO o eixo que
diverge. Puro, sem rede — laudos sintéticos.
"""
from __future__ import annotations

import pytest

from webqa.comparador import comparar, motivos_de_incompatibilidade

pytestmark = pytest.mark.verification


def _laudo(versao="1.0.0", hash_="sha256:aaa", alvos=None):
    return {"padrao": {"versao": versao, "commit": "abc1234",
                       "caminhos_sensiveis_hash": hash_, "caminhos_total": 8},
            "alvos": alvos or [], "correlacoes": []}


def _alvo(executado, esperado, findings=()):
    return {"alvo": "https://x", "esperado": esperado, "executado": executado,
            "findings": [{"tipo": "exposicao:vcs", "recurso": "https://x/.git",
                          "severidade": s} for s in findings]}


def test_recusa_versao_diferente():
    r = comparar(_laudo(versao="1.0.0"), _laudo(versao="1.1.0"))
    assert r["comparavel"] is False
    assert any("versão do padrão difere" in m for m in r["motivos"])
    assert "projetos" not in r                      # nada agregado quando incomparável


def test_recusa_hash_de_lista_diferente():
    r = comparar(_laudo(hash_="sha256:aaa"), _laudo(hash_="sha256:bbb"))
    assert r["comparavel"] is False
    assert any("hash da lista curada difere" in m for m in r["motivos"])


def test_recusa_laudo_sem_carimbo():
    sem = {"alvos": [], "correlacoes": []}          # sem bloco `padrao`
    r = comparar(sem, _laudo())
    assert r["comparavel"] is False
    assert any("sem carimbo de régua" in m for m in r["motivos"])


def test_compara_sob_regua_comum_a_cobertura_de_sondagem():
    a = _laudo(alvos=[_alvo(executado=91, esperado=91)])
    b = _laudo(alvos=[_alvo(executado=38, esperado=91)])
    r = comparar(a, b, rotulo_a="proj-a", rotulo_b="proj-b")
    assert r["comparavel"] is True
    assert r["regua"] == {"versao": "1.0.0", "caminhos_sensiveis_hash": "sha256:aaa"}
    assert r["projetos"]["proj-a"]["cobertura"] == {"executado": 91, "esperado": 91}
    assert r["projetos"]["proj-b"]["cobertura"] == {"executado": 38, "esperado": 91}


def test_lado_a_lado_de_achados_por_severidade():
    a = _laudo(alvos=[_alvo(1, 1, findings=("alta", "media"))])
    b = _laudo(alvos=[_alvo(1, 1, findings=("alta",))])
    r = comparar(a, b)
    assert r["projetos"]["A"]["por_severidade"] == {"alta": 1, "media": 1}
    assert r["projetos"]["B"]["por_severidade"] == {"alta": 1}


def test_motivos_vazio_quando_reguas_batem():
    assert motivos_de_incompatibilidade(_laudo(), _laudo()) == []
