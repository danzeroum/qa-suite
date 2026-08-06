"""VERIFICAÇÃO: a guarda de coletores órfãos pega o que existe para pegar (OS-52).

Ela nasceu VERMELHA contra o `main` real — `webqa/i18n.py::JS_PSEUDO_LOCALIZAR`
entrou na parte 2 sem check que o executasse. Vermelho histórico, não mutação
plantada: a guarda foi escrita depois do defeito e o acusou onde ele estava.
"""
import ast

import pytest

from scripts.afere_simbolos import (
    _nomes_usados,
    coletores_de,
    consumidores_de,
    problemas,
    resumo,
)

pytestmark = pytest.mark.verification


def _arvore(tmp_path, arquivos: dict):
    for caminho, conteudo in arquivos.items():
        alvo = tmp_path / caminho
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")
    for pasta in ("webqa", "checks", "scripts", "fixture_target"):
        (tmp_path / pasta).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_coletor_orfao_reprova(tmp_path):
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n'})
    achados, placar = problemas(raiz, allowlist={})
    assert placar["orfaos"] == ["m.py::JS_X"]
    assert len(achados) == 1 and "m.py::JS_X" in achados[0]


def test_coletor_consumido_por_check_passa(tmp_path):
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n',
                              "checks/test_a.py": "from webqa.m import JS_X\nprint(JS_X)\n"})
    achados, placar = problemas(raiz, allowlist={})
    assert achados == [] and placar["orfaos"] == []


def test_coletor_consumido_so_por_tests_reprova(tmp_path):
    """É o ponto da guarda: coletor coberto só por unidade continua sendo um
    instrumento que a suíte nunca aponta para um alvo."""
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n',
                              "tests/test_m.py": "from webqa.m import JS_X\nassert JS_X\n"})
    achados, _ = problemas(raiz, allowlist={})
    assert len(achados) == 1


def test_consumo_intra_webqa_conta(tmp_path):
    """Um coletor pode compor outro; o que se cobra é que exista cadeia."""
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n',
                              "webqa/n.py": "from webqa.m import JS_X\nJS_Y = JS_X\n",
                              "checks/test_a.py": "from webqa.n import JS_Y\nprint(JS_Y)\n"})
    achados, _ = problemas(raiz, allowlist={})
    assert achados == []


def test_citacao_em_docstring_nao_conta_como_consumo(tmp_path):
    """O caso que a própria guarda produziu: o docstring dela CITAVA o símbolo
    ao explicar o defeito, e a busca textual a fazia se enxergar como
    consumidora. Explicar não é fazer; citar não é executar."""
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n',
                              "checks/test_a.py": '"""Fala de JS_X mas não o usa."""\n'})
    achados, _ = problemas(raiz, allowlist={})
    assert len(achados) == 1, "citação em prosa não pode dispensar a guarda"


def test_allowlist_com_motivo_passa(tmp_path):
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n'})
    achados, placar = problemas(raiz, allowlist={"m.py::JS_X": "entra na OS seguinte"})
    assert achados == [] and placar["dispensados"] == ["m.py::JS_X"]


def test_allowlist_sem_motivo_reprova(tmp_path):
    """Dispensa que ninguém consegue revisar depois é dispensa que não vale."""
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "()=>1"\n'})
    achados, _ = problemas(raiz, allowlist={"m.py::JS_X": "  "})
    assert achados and any("JS_X" in a for a in achados)


def test_allowlist_de_simbolo_inexistente_reprova(tmp_path):
    """Dispensa órfã esconde a próxima de verdade."""
    raiz = _arvore(tmp_path, {"webqa/m.py": "X = 1\n"})
    achados, _ = problemas(raiz, allowlist={"m.py::JS_SUMIU": "motivo"})
    assert any("não existe mais" in a for a in achados)


def test_nomes_usados_ignora_prosa_e_pega_referencia():
    assert _nomes_usados('"""JS_A"""\nJS_B\n') == {"JS_B"}


def test_nomes_usados_pega_import_e_atributo():
    usados = _nomes_usados("from m import JS_C\nm.JS_D\n")
    assert {"JS_C", "JS_D"} <= usados


def test_coletores_de_so_pega_prefixo_js(tmp_path):
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "a"\nOUTRO = "b"\n_JS_Y = "c"\n'})
    assert list(coletores_de(raiz)) == ["m.py::JS_X"]


def test_o_arquivo_que_define_nao_conta_como_consumidor(tmp_path):
    raiz = _arvore(tmp_path, {"webqa/m.py": 'JS_X = "a"\nUSO = JS_X\n'})
    assert consumidores_de("m.py::JS_X", {"webqa/m.py": (raiz / "webqa/m.py").read_text()}) == ()


def test_placar_sai_sempre():
    _, placar = problemas(allowlist={})
    assert "coletores JS_" in resumo(placar)


def test_o_repositorio_esta_limpo():
    """A guarda contra o repositório de verdade. Vermelha no commit em que
    nasceu, verde quando o check que consome o coletor existir."""
    achados, _ = problemas()
    assert achados == [], "\n".join(achados)


def test_a_guarda_e_analise_estatica_e_nao_importa_nada():
    """Ela lê AST; importar os módulos exigiria Playwright e transformaria uma
    pergunta de estrutura numa execução."""
    fonte = (__import__("pathlib").Path(__file__).resolve().parent.parent
             / "scripts" / "afere_simbolos.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    importados = {n.module for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any((m or "").startswith("webqa") for m in importados)
