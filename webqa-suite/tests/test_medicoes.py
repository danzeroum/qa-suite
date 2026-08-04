"""VERIFICAÇÃO do emissor de medição do motor (D5k wiring).

Os transformadores são puros: recebem o JSON da ferramenta (coverage.py, ruff
C901) e devolvem os blocos que o cockpit exibe. Sem rede, sem subprocess nos
testes de transformação — só a montagem integra as fontes.
"""
from __future__ import annotations

import pytest

from scripts.medicoes import (
    cobertura_de,
    complexidade_de,
    montar_medicoes,
)

pytestmark = pytest.mark.verification


def test_cobertura_de_transforma_o_json_do_coverage():
    cov = {"totals": {"percent_covered": 77.4},
           "files": {"webqa/metricas.py": {"summary": {"percent_covered": 7.0}},
                     "webqa/gates.py": {"summary": {"percent_covered": 100.0}}}}
    bloco = cobertura_de(cov)
    assert bloco["total"] == 77.4
    assert bloco["por_arquivo"]["webqa/metricas.py"] == 7.0
    assert "verification" in bloco["vies"]          # o viés é nomeado, não some


def test_complexidade_de_ordena_a_cauda_e_marca_o_teto():
    itens = [
        {"code": "C901", "filename": "webqa/a.py", "message": "`f` is too complex (5 > 0)"},
        {"code": "C901", "filename": "webqa/b.py", "message": "`g` is too complex (11 > 0)"},
        {"code": "E501", "filename": "webqa/c.py", "message": "linha longa"},  # ignorado
    ]
    bloco = complexidade_de(itens, teto=8, topn=12)
    assert bloco["teto"] == 8
    assert [c["cc"] for c in bloco["cauda"]] == [11, 5]     # maior CC primeiro
    assert bloco["cauda"][0]["func"] == "g"
    # o de código não-C901 não entra
    assert all(c["func"] in ("f", "g") for c in bloco["cauda"])


def test_complexidade_de_respeita_o_topn():
    itens = [{"code": "C901", "filename": "x.py", "message": f"`f{i}` is too complex ({i} > 0)"}
             for i in range(1, 30)]
    bloco = complexidade_de(itens, topn=5)
    assert len(bloco["cauda"]) == 5
    assert bloco["cauda"][0]["cc"] == 29                    # os maiores


def test_montar_medicoes_omite_bloco_sem_fonte(tmp_path):
    """Sem coverage.json, sem mutacao.json e sem webqa/ para o ruff: nenhum bloco.
    O cockpit então mostra os três como 'não instrumentada' — nunca 0%."""
    med = montar_medicoes(tmp_path)
    assert "cobertura_codigo" not in med               # sem coverage.json
    assert "mutacao" not in med                         # sem mutacao.json


def test_montar_medicoes_le_cobertura_quando_presente(tmp_path):
    rep = tmp_path / "report"
    rep.mkdir()
    (rep / "coverage.json").write_text(
        '{"totals":{"percent_covered":80.0},"files":{}}', encoding="utf-8")
    med = montar_medicoes(tmp_path)
    assert med["cobertura_codigo"]["total"] == 80.0
