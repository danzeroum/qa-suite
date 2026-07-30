"""VERIFICAÇÃO (nível sistema): as dimensões lgpd e seguranca detectam o que prometem detectar.

Este é o teste mais valioso da suíte e o mais desconfortável de escrever: sobe um
alvo com violações conhecidas, roda a dimensão inteira contra ele e exige que os
FAILs sejam EXATAMENTE os do contrato (`fixture_target/esperado.json`).

Os dois erros que ele pega e que nenhum teste de unidade pega:

* **a mais** — um check passou a reprovar algo que não é violação; em produção
  isso reprova alvo conforme e queima a credibilidade da bateria;
* **a menos** — um check parou de detectar (regex quebrada, fixture mudada,
  refatoração silenciosa) e a suíte segue verde, aprovando alvo não conforme.
  É o risco R7 aplicado à dimensão lgpd.

O pytest interno roda em SUBPROCESSO com WEBQA_REPORT_DIR próprio: rodar pytest
dentro de pytest compartilharia o estado do plugin de relatório e sobrescreveria
o artefato da execução externa.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fixture_target.servir import AlvoFixture

pytestmark = [pytest.mark.verification, pytest.mark.browser]

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = RAIZ / "fixture_target" / "esperado.json"


@pytest.fixture(scope="module")
def contrato() -> dict:
    return json.loads(CONTRATO.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def execucao(tmp_path_factory) -> dict:
    """Sobe o alvo fixture, roda `pytest -m "lgpd or seguranca"` contra ele e devolve o summary."""
    pytest.importorskip("playwright", reason="Playwright ausente: teste de sistema exige navegador.")
    saida = tmp_path_factory.mktemp("alvo-fixture")

    with AlvoFixture() as alvo:
        env = {
            **os.environ,
            "WEBQA_TARGET_URL": alvo.url,
            "WEBQA_REPORT_DIR": str(saida),
            # 127.0.0.1 nunca deve passar por proxy corporativo/agente.
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-m", "lgpd or seguranca", "-p", "no:cacheprovider", "-q"],
            cwd=RAIZ, env=env, capture_output=True, text=True, timeout=900,
        )

    summary = saida / "summary.json"
    if not summary.exists():  # pragma: no cover - diagnóstico de ambiente
        pytest.fail(
            "execução interna não gerou summary.json.\n"
            f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
        )
    dados = json.loads(summary.read_text(encoding="utf-8"))

    # O skip mora AQUI, na fixture, e não em cada teste: sem navegador, metade
    # dos checks vira skip e o contrato ficaria "a menos" por motivo de
    # ambiente — reprovando o quality-gate, que roda sem Chromium instalado.
    sem_navegador = [
        r["test"] for r in dados["results"]
        if r.get("browser") and r["outcome"] == "skipped"
        and "Chromium indispon" in (r.get("detail") or "")
    ]
    if sem_navegador:
        pytest.skip(
            f"Chromium indisponível ({len(sem_navegador)} testes pulados na execução "
            "interna): rode `python -m playwright install chromium`. O contrato do "
            "fixture não pode ser conferido sem navegador."
        )
    return dados


def _por_id(execucao: dict) -> dict[str, str]:
    """{test_id: outcome} — sem o prefixo de caminho variável."""
    return {r["test"]: r["outcome"] for r in execucao["results"]}


def test_execucao_interna_exercitou_o_navegador(execucao):
    """Contrato conferido sem nenhum teste de navegador seria contrato vazio."""
    com_browser = [r for r in execucao["results"] if r.get("browser")]
    assert len(com_browser) >= 4, (
        f"apenas {len(com_browser)} testes de navegador na execução interna — "
        "a dimensão browser não foi exercida de verdade."
    )


def test_contrato_lista_apenas_testes_existentes(execucao, contrato):
    """esperado.json com id inexistente é erro de CONFIGURAÇÃO, não passe silencioso."""
    coletados = set(_por_id(execucao))
    declarados = set(contrato["devem_falhar"]) | set(contrato["fora_do_contrato"])
    fantasmas = sorted(declarados - coletados)
    assert not fantasmas, (
        f"esperado.json declara testes que não existem na execução: {fantasmas}. "
        "Corrija o contrato (ou o nome do teste) — um id fantasma esconderia a "
        "violação que ele deveria cobrar."
    )


def test_fails_observados_sao_exatamente_os_esperados(execucao, contrato):
    por_id = _por_id(execucao)
    fora = set(contrato["fora_do_contrato"])
    observados = {t for t, outcome in por_id.items() if outcome == "failed"} - fora
    esperados = set(contrato["devem_falhar"])

    a_menos = sorted(esperados - observados)   # check parou de detectar
    a_mais = sorted(observados - esperados)    # check reprovando o que não devia
    assert not (a_menos or a_mais), (
        "Contrato do alvo fixture violado.\n"
        f"NÃO reprovaram, mas deveriam ({len(a_menos)}): {a_menos}\n"
        "  → a violação segue no HTML e o check deixou de detectá-la, "
        "ou a violação foi removida do fixture sem atualizar esperado.json.\n"
        f"Reprovaram, mas não deveriam ({len(a_mais)}): {a_mais}\n"
        "  → o check passou a reprovar comportamento conforme (falso positivo)."
    )


def test_transparencia_passa_no_fixture(execucao):
    """O fixture é não conforme em consentimento/PII, mas CONFORME em
    transparência: o contrato precisa provar os dois lados, senão um check que
    reprova tudo passaria por 'funcionando'."""
    por_id = _por_id(execucao)
    for teste in (
        "checks/lgpd/test_transparencia.py::test_politica_acessivel",
        "checks/lgpd/test_transparencia.py::test_direitos_do_titular",
        "checks/lgpd/test_transparencia.py::test_canal_encarregado",
    ):
        assert por_id.get(teste) == "passed", (
            f"{teste} deveria passar contra o fixture (política completa, direitos "
            f"do Art. 18 e canal do encarregado presentes), mas saiu '{por_id.get(teste)}'."
        )
