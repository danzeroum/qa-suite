"""VERIFICAÇÃO: exportador de conformidade e a guarda do mapa (OS-53).

Sobre `summary.json` FABRICADO — sem navegador, sem rede, sem alvo. O que se fixa
aqui é a decisão que dá sentido ao documento inteiro: **só `failed` vira achado**.
`xfailed` é veredito adiado por ambiente e `skipped` é não-avaliado; exportá-los
transformaria "a suíte decidiu não afirmar" e "ninguém mediu" em defeito medido.
"""
import json

import pytest

from webqa.conformidade import (
    CAMPO_NODEID,
    EXIGE_HUMANO,
    NOTA_EPISTEMICA,
    achados_de,
    carregar_mapa,
    linhas_do_vpat,
    para_sarif,
    placar_do_mapa,
    problemas_do_mapa,
    resumo,
)
from webqa.sarif import SCHEMA_SARIF, VERSAO_SARIF

pytestmark = pytest.mark.verification

MAPA = {
    "criterios": {"2.4.7": {"nome": "Foco visível", "nodeids": ["checks/gui/t.py::test_foco"]}},
    "exige_humano": {"4.1.2": {"nome": "Nome, função, valor", "motivo": "exige leitor real"}},
    "sem_criterio": {"checks/gui/t.py::test_outro": "Core Web Vitals, não WCAG"},
}


def _laudo(*pares):
    return {"generated_at": "2026-01-01 00:00:00", "alvo": "http://alvo",
            "results": [{"dimension": "gui", CAMPO_NODEID: n, "outcome": o,
                         "detail": f"detalhe de {n}"} for n, o in pares]}


# ---------- a decisão: só `failed` vira achado ----------

def test_failed_vira_achado_com_criterio():
    achados = achados_de(_laudo(("checks/gui/t.py::test_foco", "failed")), MAPA)
    assert len(achados) == 1
    assert achados[0]["criterio"] == "2.4.7" and achados[0]["criterio_nome"] == "Foco visível"


@pytest.mark.parametrize("desfecho", ["passed", "xfailed", "skipped", "error"])
def test_os_outros_desfechos_nao_viram_achado(desfecho):
    assert achados_de(_laudo(("checks/gui/t.py::test_foco", desfecho)), MAPA) == ()


def test_dimensao_alheia_nao_entra():
    laudo = {"results": [{"dimension": "lgpd", CAMPO_NODEID: "x", "outcome": "failed"}]}
    assert achados_de(laudo, MAPA) == ()


def test_failed_sem_criterio_entra_com_regra_propria():
    """Ele é defeito de interface e aparece; o que não se inventa é o critério."""
    achados = achados_de(_laudo(("checks/gui/t.py::test_outro", "failed")), MAPA)
    assert len(achados) == 1 and achados[0]["criterio"] == ""


# ---------- SARIF ----------

def test_sarif_reusa_schema_e_versao_do_modulo_dono():
    doc = para_sarif(_laudo(("checks/gui/t.py::test_foco", "failed")), MAPA)
    assert doc["$schema"] == SCHEMA_SARIF and doc["version"] == VERSAO_SARIF


def test_sarif_tem_os_campos_minimos():
    doc = para_sarif(_laudo(("checks/gui/t.py::test_foco", "failed")), MAPA)
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"]
    assert run["results"][0]["ruleId"] == "WCAG-2.4.7"
    assert run["results"][0]["message"]["text"]
    assert run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]


def test_sarif_nao_repete_regra_para_dois_achados_do_mesmo_criterio():
    laudo = _laudo(("checks/gui/t.py::test_foco", "failed"))
    laudo["results"].append({"dimension": "gui", CAMPO_NODEID: "checks/gui/t.py::test_foco",
                             "outcome": "failed", "detail": "de novo"})
    regras = para_sarif(laudo, MAPA)["runs"][0]["tool"]["driver"]["rules"]
    assert len(regras) == 1


def test_sarif_de_laudo_limpo_sai_vazio_e_valido():
    doc = para_sarif(_laudo(("checks/gui/t.py::test_foco", "passed")), MAPA)
    assert doc["runs"][0]["results"] == []
    json.dumps(doc)          # serializa


# ---------- VPAT ----------

def test_vpat_traz_os_tres_estados_e_o_exige_humano_aparece():
    linhas = linhas_do_vpat(_laudo(("checks/gui/t.py::test_foco", "failed")), MAPA)
    estados = {x["estado"] for x in linhas}
    assert EXIGE_HUMANO in estados, "omitir os exige-humano fingiria completude"
    assert any(x["criterio"] == "4.1.2" for x in linhas)


def test_criterio_com_teste_que_pulou_nao_vira_conforme():
    """Contar skip como conforme transformaria ausência de medida em atestado."""
    linha = next(x for x in linhas_do_vpat(_laudo(("checks/gui/t.py::test_foco", "skipped")),
                                           MAPA) if x["criterio"] == "2.4.7")
    assert "não avaliado" in linha["situacao"]


def test_criterio_ausente_da_campanha_diz_que_nao_executou():
    linha = next(x for x in linhas_do_vpat(_laudo(), MAPA) if x["criterio"] == "2.4.7")
    assert "não executado" in linha["situacao"]


def test_criterio_que_passou_diz_conforme_na_MEDIDA():
    linha = next(x for x in linhas_do_vpat(_laudo(("checks/gui/t.py::test_foco", "passed")),
                                           MAPA) if x["criterio"] == "2.4.7")
    assert "conforme na medida automatizada" in linha["situacao"]


def test_a_nota_epistemica_nao_promete_certificado():
    assert "não é certificado" in NOTA_EPISTEMICA or "não é a declaração" in NOTA_EPISTEMICA
    assert "EVIDÊNCIA QUE CONTRIBUI" in NOTA_EPISTEMICA


# ---------- guarda bidirecional do mapa ----------

def test_nodeid_citado_que_a_coleta_nao_produz_reprova():
    problemas = problemas_do_mapa(MAPA, ["checks/gui/t.py::test_outro"])
    assert any("test_foco" in p and "não produz" in p for p in problemas)


def test_check_coletado_fora_do_mapa_reprova():
    problemas = problemas_do_mapa(
        MAPA, ["checks/gui/t.py::test_foco", "checks/gui/t.py::test_outro",
               "checks/gui/t.py::test_novo"])
    assert any("test_novo" in p and "não conhece" in p for p in problemas)


def test_estado_saudavel_nao_reprova_e_o_placar_bate():
    coletados = ["checks/gui/t.py::test_foco", "checks/gui/t.py::test_outro"]
    assert problemas_do_mapa(MAPA, coletados) == []
    placar = placar_do_mapa(MAPA, coletados)
    assert placar["criterios"] == 1 and placar["sem_criterio"] == 1
    assert "critério(s) com teste" in resumo(placar)


def test_exige_humano_sem_motivo_reprova():
    mapa = {**MAPA, "exige_humano": {"4.1.2": {"nome": "x", "motivo": "  "}}}
    assert any("sem motivo" in p for p in problemas_do_mapa(mapa, [
        "checks/gui/t.py::test_foco", "checks/gui/t.py::test_outro"]))


def test_sem_criterio_sem_motivo_reprova():
    mapa = {**MAPA, "sem_criterio": {"checks/gui/t.py::test_outro": ""}}
    assert any("sem motivo" in p for p in problemas_do_mapa(mapa, [
        "checks/gui/t.py::test_foco", "checks/gui/t.py::test_outro"]))


def test_o_mapa_do_repositorio_carrega_e_tem_os_tres_blocos():
    mapa = carregar_mapa()
    assert mapa["criterios"] and mapa["exige_humano"] and mapa["sem_criterio"]


# ---------- o PDF renderiza arquivo local ----------

def test_o_vpat_nao_faz_requisicao_externa(tmp_path):
    """Mesma disciplina do `summary.html`: imprimível offline, sem fonte remota
    nem folha externa. Um PDF que dependesse da rede sairia diferente conforme o
    dia, e evidência que muda sozinha não é evidência."""
    import re
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from scripts.exporta_conformidade import vpat_html
    html = vpat_html(_laudo(("checks/gui/t.py::test_foco", "failed")), MAPA)
    assert not re.search(r"""(src|href)\s*=\s*["']https?://""", html)
    assert "EVIDÊNCIA QUE CONTRIBUI" in html, "a nota precisa estar na capa"


def test_o_mapa_cobre_a_COLETA_REAL_de_gui():
    """A guarda contra o repositório de verdade, nos dois sentidos.

    Lê a coleta por AST — não roda pytest dentro de pytest, e não precisa de
    navegador para responder "quais checks de `gui` existem".
    """
    import ast
    from pathlib import Path as _P
    raiz = _P(__file__).resolve().parent.parent
    coletados = []
    for arquivo in sorted((raiz / "checks" / "gui").glob("test_*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        for no in ast.parse(fonte).body:
            if isinstance(no, ast.FunctionDef) and no.name.startswith("test"):
                coletados.append(f"checks/gui/{arquivo.name}::{no.name}")
        # pytest-bdd gera um teste por cenário: os nomes vêm da feature, não do
        # módulo, então a leitura por AST não os enxerga. Eles entram pelo mapa.
    declarados = set(carregar_mapa()["sem_criterio"]) | {
        n for d in carregar_mapa()["criterios"].values() for n in d["nodeids"]}
    faltando = sorted(set(coletados) - declarados)
    assert not faltando, (
        "check(s) de gui que o mapa de conformidade não conhece: " + str(faltando))
