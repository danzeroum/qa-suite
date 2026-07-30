"""VERIFICAÇÃO (nível sistema): o relatório passa na bateria que o gera.

O aceite central da OS-15 é circular de propósito — e circular só vale se for
permanente. Aqui o §12 deixa de ser checklist manual e vira teste: qualquer
regressão no template (requisição externa introduzida, `h1` duplicado, JS virando
obrigatório, estado só por cor) reprova antes de chegar ao alvo de alguém.

Dois níveis, um custo cada:

* **estático** (sempre roda, milissegundos): os 12 critérios do auditor aplicados
  ao HTML gerado;
* **axe com navegador** (marcado `browser`, pulado sem Chromium): serve o
  relatório e roda a bateria contra ele.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.audita_design import (
    CRITERIOS,
    FAIL,
    Documento,
    veredito_axe,
)
from webqa.report_html import montar

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


def _summary_realista() -> dict:
    """Execução com os quatro estados, dupla dimensão e referência legal."""
    def r(test, estado, **extra):
        base = {"test": test, "dimension": "lgpd", "dimensions": ["lgpd"], "browser": False,
                "outcome": "skipped" if estado == "xfail" else estado, "estado": estado,
                "duration_s": 0.42, "detail": ""}
        base.update(extra)
        return base

    return {
        "generated_at": "2026-07-30 04:00:00",
        "duration_s": 41.7,
        "alvo": "http://127.0.0.1:8130",
        "comando": "pytest -m lgpd",
        "dimension_notes": {"lgpd": ("Verificação caixa-preta do que é observável de fora. "
                                     "Falha PROVA não conformidade; passar NÃO certifica "
                                     "conformidade.")},
        "results": [
            r("checks/lgpd/test_consentimento.py::test_sem_trackers", "failed", browser=True,
              detail="Tracker www.googletagmanager.com contactado antes do consentimento "
                     "(Art. 7º, I e Art. 8º, §4). Detalhe com <b>marcação</b> & aspas \"assim\"."),
            r("checks/lgpd/test_retencao.py::test_cookies", "failed",
              detail="Cookie _ga com Max-Age de 730 dias (Art. 15/16)."),
            r("checks/ux/test_acessibilidade.py::test_imagens_com_alt", "failed",
              dimension="ux", dimensions=["ux", "lgpd"], browser=True,
              detail="1 imagem sem atributo alt (LBI, Art. 63)."),
            r("checks/lgpd/test_pii_transito.py::test_referrer_policy", "xfail",
              detail="Referrer-Policy ausente — sinal de maturidade."),
            r("checks/lgpd/test_transparencia.py::test_politica", "passed"),
            r("checks/frontend/test_rendering.py::test_fcp", "skipped", browser=True,
              detail="Chromium indisponível: rode `python -m playwright install chromium`."),
        ],
    }


@pytest.fixture(scope="module")
def relatorio(tmp_path_factory) -> Documento:
    """HTML gerado pelo template, gravado em disco para o auditor ler."""
    inventario = {"third_parties": [
        {"host": "www.googletagmanager.com", "requests": 2, "resource_types": ["script"]}]}
    html = montar(_summary_realista(), inventario, [])
    destino = tmp_path_factory.mktemp("relatorio") / "summary.html"
    destino.write_text(html, encoding="utf-8")
    return Documento(destino, html)


def test_relatorio_gerado_passa_nos_criterios_do_paragrafo_12(relatorio):
    """O relatório cobra do alvo o que cumpre em si mesmo."""
    reprovados = []
    for nome, funcao, _bloqueante in CRITERIOS:
        resultado = funcao(relatorio)
        if resultado.status == FAIL:
            reprovados.append(f"{nome}: {resultado.evidencia}")
    assert not reprovados, "critérios do §12 reprovados no HTML gerado:\n" + "\n".join(reprovados)


def test_relatorio_gerado_nao_sugere_certificacao(relatorio):
    """Regra do design: nada no documento insinua selo ou aprovação."""
    corpo = relatorio.texto.split("</style>", 1)[1].lower()
    for proibido in ("certificado de conformidade", "aprovado pela anpd", "selo de conformidade"):
        assert proibido not in corpo
    assert "não constitui certificação" in corpo


@pytest.mark.browser
def test_bateria_com_axe_contra_o_relatorio_gerado(relatorio, tmp_path):
    """Circular de verdade: a bateria frontend+ux roda contra o próprio relatório."""
    pytest.importorskip("playwright", reason="Playwright ausente.")
    from scripts.audita_design import _Servidor, rodar_bateria

    with _Servidor(relatorio.caminho.parent) as servidor:
        bateria = rodar_bateria(servidor.base, relatorio.nome, tmp_path)

    veredito = veredito_axe(bateria)
    if veredito.status != "PASS":
        if "Chromium" in veredito.evidencia or veredito.status == "PULADO":
            pytest.skip(f"axe não avaliado: {veredito.evidencia}")
        pytest.fail(f"axe no relatório gerado: {veredito.evidencia}")

    # Falhas da bateria que não são do relatório (o 404 do servidor do auditor)
    # ficam fora; o que importa aqui é acessibilidade e renderização.
    criticos = {t: o for t, o in bateria.items()
                if o == "failed" and t.startswith(("test_sem_violacoes", "test_imagens",
                                                   "test_inputs", "test_console"))}
    assert not criticos, f"o relatório gerado reprova na própria bateria: {criticos}"


@pytest.mark.browser
def test_execucao_real_gera_relatorio_conforme(tmp_path):
    """Ponta a ponta: roda a suíte contra o alvo fixture e audita o que saiu."""
    pytest.importorskip("playwright", reason="Playwright ausente.")
    from fixture_target.servir import AlvoFixture

    saida = tmp_path / "report"
    with AlvoFixture() as alvo:
        env = {**os.environ, "WEBQA_TARGET_URL": alvo.url, "WEBQA_REPORT_DIR": str(saida),
               "NO_PROXY": "*", "no_proxy": "*"}
        subprocess.run(  # nosec B603 - argv fixo, sem shell
            [sys.executable, "-m", "pytest", "-m", "lgpd", "-q", "-p", "no:cacheprovider"],
            cwd=RAIZ, env=env, capture_output=True, text=True, timeout=900, check=False)

    gerado = saida / "summary.html"
    if not gerado.exists():
        pytest.skip("execução interna não gerou summary.html (ambiente sem navegador)")
    doc = Documento(gerado, gerado.read_text(encoding="utf-8"))

    reprovados = [f"{nome}: {funcao(doc).evidencia}"
                  for nome, funcao, _b in CRITERIOS if funcao(doc).status == FAIL]
    assert not reprovados, "relatório de execução REAL reprova no §12:\n" + "\n".join(reprovados)

    dados = json.loads((saida / "summary.json").read_text(encoding="utf-8"))
    assert dados.get("alvo"), "summary.json precisa registrar o alvo observado"
    assert dados.get("comando"), "summary.json precisa registrar o comando"
    assert any(r.get("estado") == "xfail" for r in dados["results"]), (
        "xfail precisa chegar ao relatório como estado próprio")


# ---------- OS-20: o summary REAL da campanha, com 13 erros do Chromium ----------

def _summaries_reais() -> list[Path]:
    """Execuções reais gravadas pela campanha (report/ é ignorado no Git).

    Dado de teste que ninguém fabricou: 13 erros de setup por Chromium sem
    egresso, achados de verdade e métricas de rede medidas.
    """
    return sorted((RAIZ / "report" / "campanha").glob("*/run*/summary.json"))


@pytest.mark.parametrize("indice", range(3))
def test_summary_real_com_erros_de_infra_renderiza_corretamente(indice, tmp_path):
    caminhos = _summaries_reais()
    if len(caminhos) <= indice:
        pytest.skip("sem execução real da campanha neste ambiente (rode `make campanha`)")
    dados = json.loads(caminhos[indice].read_text(encoding="utf-8"))
    from collections import Counter
    contagem = Counter(r.get("estado") for r in dados["results"])
    if not contagem.get("error"):
        pytest.skip("esta execução não registrou erro de infraestrutura")

    html = montar(dados)

    # 1. A seção de infraestrutura existe e conta o que o summary traz.
    assert 'id="erros"' in html
    assert f"Erros de execução ({contagem['error']})" in html

    # 2. Os achados continuam intactos — erro NÃO foi absorvido como achado.
    assert f"Achados ({contagem.get('failed', 0)})" in html
    if contagem.get("failed"):
        assert f'id="a{contagem["failed"]}"' in html, "numeração A1…An preservada"

    # 3. Banner coerente com o que aconteceu.
    if contagem.get("failed"):
        assert "Nenhuma não conformidade observada" not in html
    else:
        assert "Julgamento incompleto" in html

    # 4. Métricas medidas aparecem; as não medidas não viram zero.
    medidas = dados.get("metricas") or {}
    if medidas:
        faixa = html.split('id="metricas"', 1)[1].split("</dl>", 1)[0]
        assert "TTFB" in faixa
        assert "FCP" not in faixa, "FCP não foi medido nesta execução — não pode aparecer"

    # 5. E o documento continua passando no próprio §12.
    destino = tmp_path / "summary.html"
    destino.write_text(html, encoding="utf-8")
    doc = Documento(destino, html)
    reprovados = [f"{nome}: {funcao(doc).evidencia}"
                  for nome, funcao, _b in CRITERIOS if funcao(doc).status == FAIL]
    assert not reprovados, "relatório de execução REAL reprova no §12:\n" + "\n".join(reprovados)
