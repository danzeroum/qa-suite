"""VERIFICAÇÃO do catálogo por AST (D1k) — as derivações que o cockpit veste.

Verificação: catálogos sintéticos de borda em tmp_path (sem repo real).
Validação: dogfooding contra o catalogo.json real fica na tela lado a lado do
protótipo; aqui as derivações são exercitadas em árvores fabricadas.
"""
from __future__ import annotations

import json

import pytest

from scripts.catalogo import _descritiva, montar_catalogo

pytestmark = pytest.mark.verification


def _repo(tmp_path, arquivos: dict[str, str], summary: dict | None = None):
    for rel, conteudo in arquivos.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")
    if summary is not None:
        rep = tmp_path / "report"
        rep.mkdir(parents=True, exist_ok=True)
        (rep / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return montar_catalogo(tmp_path)


def _por_funcao(cat, nome):
    return next(t for t in cat["testes"] if t["funcao"] == nome)


def test_populacao_por_diretorio_nunca_por_string(tmp_path):
    cat = _repo(tmp_path, {
        "checks/frontend/test_x.py": "def test_alvo(): pass\n",
        "tests/test_y.py": "def test_suite(): pass\n"})
    assert _por_funcao(cat, "test_alvo")["populacao"] == "alvo"
    assert _por_funcao(cat, "test_suite")["populacao"] == "suite"
    # As populações não se somam: o agregado as mantém separadas, sem total combinado.
    assert set(cat["agregados"]["populacoes"]) == {"alvo", "suite"}
    assert "total" not in cat["agregados"]["populacoes"]


def test_nivel_precedencia(tmp_path):
    cat = _repo(tmp_path, {
        "checks/acceptance/test_a.py":
            "import pytest\npytestmark=pytest.mark.acceptance\ndef test_ac(): pass\n",
        "checks/frontend/test_b.py": "import pytest\n@pytest.mark.browser\ndef test_br(): pass\n",
        "checks/backend/test_c.py": "import pytest\n@pytest.mark.load\ndef test_ld(): pass\n",
        "checks/backend/test_d.py": "def test_int(): pass\n",
        "tests/test_e.py": "def test_un(): pass\n"})
    assert _por_funcao(cat, "test_ac")["nivel"] == "aceitacao"
    assert _por_funcao(cat, "test_br")["nivel"] == "sistema"      # browser
    assert _por_funcao(cat, "test_ld")["nivel"] == "sistema"      # load
    assert _por_funcao(cat, "test_int")["nivel"] == "integracao"  # checks/, sem browser/load
    assert _por_funcao(cat, "test_un")["nivel"] == "unidade"


def test_dimensoes_em_ordem_de_declaracao_sem_browser_nem_builtins(tmp_path):
    cat = _repo(tmp_path, {"checks/ux/test_x.py":
        "import pytest\npytestmark=[pytest.mark.ux, pytest.mark.lgpd, pytest.mark.browser]\n"
        "@pytest.mark.parametrize('n',[1,2])\ndef test_z(n): pass\n"})
    t = _por_funcao(cat, "test_z")
    assert t["dimensoes"] == ["ux", "lgpd"]          # ordem de declaração, browser fora
    assert "parametrize" not in t["dimensoes"]       # builtin do pytest não é dimensão
    assert t["atributos"] == ["browser"]             # atributos ordenados


def test_casos_e_produto_de_parametrize(tmp_path):
    cat = _repo(tmp_path, {"tests/test_p.py":
        "import pytest\n"
        "@pytest.mark.parametrize('a',[1,2,3])\ndef test_um(a): pass\n"
        "@pytest.mark.parametrize('a',[1,2])\n@pytest.mark.parametrize('b',[1,2])\n"
        "def test_dois(a,b): pass\ndef test_zero(): pass\n"})
    assert _por_funcao(cat, "test_um")["casos"] == 3
    assert _por_funcao(cat, "test_dois")["casos"] == 4    # produto 2×2
    assert _por_funcao(cat, "test_zero")["casos"] == 1
    assert cat["agregados"]["casos"] == 3 + 4 + 1


def test_veredito_condicional_conta_xfail_no_corpo(tmp_path):
    cat = _repo(tmp_path, {"tests/test_c.py":
        "import pytest\ndef test_cond():\n    if True: pytest.xfail('x')\n"
        "def test_normal(): pass\n"})
    assert _por_funcao(cat, "test_cond")["veredito_condicional"] == 1
    assert _por_funcao(cat, "test_normal")["veredito_condicional"] == 0
    assert cat["agregados"]["condicionais"] == 1


def test_garante_e_primeira_linha_do_docstring(tmp_path):
    cat = _repo(tmp_path, {"tests/test_g.py":
        'def test_com():\n    """Garante algo.\n\n    Detalhe."""\n    pass\n'
        "def test_sem(): pass\n"})
    assert _por_funcao(cat, "test_com")["garante"] == "Garante algo."
    assert _por_funcao(cat, "test_sem")["garante"] == ""
    assert cat["agregados"]["sem_contrato"] == 1


def test_gherkin_vira_cenario_de_aceitacao(tmp_path):
    cat = _repo(tmp_path, {"checks/acceptance/features/f.feature":
        "Funcionalidade: X\n  Cenário: faz algo\n    Dado y\n"})
    t = _por_funcao(cat, "faz algo")
    assert t["origem"] == "gherkin" and t["nivel"] == "aceitacao"
    assert t["dimensoes"] == ["acceptance"]
    assert cat["agregados"]["gherkin"] == 1


def test_reconciliacao_marca_estado_e_acusa_orfao(tmp_path):
    summary = {"results": [
        {"test": "tests/test_r.py::test_vivo", "outcome": "passed", "duration": 0.5},
        {"test": "tests/test_r.py::test_fantasma", "outcome": "failed", "duration": 0.1}]}
    cat = _repo(tmp_path, {"tests/test_r.py": "def test_vivo(): pass\n"}, summary=summary)
    assert _por_funcao(cat, "test_vivo")["estado"] == "passed"
    # resultado de teste que não existe mais no código não some em silêncio:
    assert cat["reconciliacao"]["orfaos"] == ["tests/test_r.py::test_fantasma"]
    assert cat["reconciliacao"]["executados"] == 1


def test_descritiva_outlier_por_tukey():
    """[0.1,0.1,0.1,9.9] → 1 outlier acima de Q3+1,5·IQR."""
    d = _descritiva([0.1, 0.1, 0.1, 9.9])
    assert d["outliers"] == 1
    assert d["n"] == 4


def test_descritiva_vazia_sem_execucao_nunca_zeros():
    assert _descritiva([]) == {}          # sem run: dict vazio, não zeros que enganam


def test_esquema_bate_com_o_catalogo_real():
    """Dogfooding leve: as chaves do meu catálogo == as do catalogo.json real."""
    from pathlib import Path
    oracle = json.loads((Path(__file__).resolve().parent.parent
                         / "docs/handoff-cockpit-dev/uploads/catalogo.json").read_text())
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "tests").mkdir()
        (Path(d) / "tests" / "test_z.py").write_text("def test_a(): pass\n")
        meu = montar_catalogo(Path(d))
    assert list(meu) == list(oracle)
    assert list(meu["agregados"]) == list(oracle["agregados"])
    assert list(meu["testes"][0]) == list(oracle["testes"][0])
