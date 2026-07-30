"""Plugin pytest: relatório consolidado de qualidade (JSON + HTML).

Observabilidade aplicada à própria suíte: cada execução deixa um artefato
inspecionável (report/summary.json e report/summary.html) com resultado por
dimensão de qualidade — backend, frontend, ux, functional, acceptance, load, lgpd.

Um teste pode pertencer a MAIS DE UMA dimensão (acessibilidade é UX e é
obrigação legal — LBI, Lei 13.146/2015 Art. 63). Nesse caso ele conta em todas
as dimensões marcadas e é agrupado na primeira declarada.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

import pytest

from webqa.metricas import coletadas
from webqa.report_html import montar
from webqa.sanitize import safe_url, sanitize_text

DIMENSIONS = (
    "backend", "frontend", "ux", "functional", "acceptance", "load", "lgpd", "verification",
)

# Honestidade epistêmica no CÓDIGO, não só na documentação: quem lê o relatório
# não leu o doc de arquitetura.
DIMENSION_NOTES = {
    "lgpd": (
        "Verificação caixa-preta do que é observável de fora. "
        "Falha PROVA não conformidade; passar NÃO certifica conformidade — "
        "base legal, contrato com operador, ROPA e governança interna não são "
        "observáveis por HTTP."
    ),
}

# Redirecionável por ambiente (12-Factor): o teste de sistema do alvo fixture
# roda um pytest interno, que sobrescreveria o relatório da execução externa.
REPORT_DIR = Path(
    os.environ.get("WEBQA_REPORT_DIR") or Path(__file__).resolve().parent.parent / "report"
)
_RESULTS: list[dict] = []
_START = time.time()


def _alvo_observado() -> str:
    """URL do alvo com a query oculta — relatório não reproduz parâmetro do alvo."""
    try:
        from webqa.config import load_settings

        return safe_url(load_settings().target_url)
    except Exception:
        return ""


def _allowlist() -> list[str]:
    """Terceiros liberados pelo controlador — a classificação do inventário respeita."""
    try:
        from webqa.config import load_settings

        return list(load_settings().lgpd_allowed_third_parties)
    except Exception:
        return []


def _comando(session) -> str:
    """Comando da execução, para o relatório dizer como reproduzir a si mesmo."""
    try:
        args = " ".join(session.config.invocation_params.args)
    except Exception:
        args = ""
    return f"pytest {args}".strip()


def report_dir() -> Path:
    """Diretório de artefatos, criado sob demanda (usado também pelos checks)."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Anexa ao report as dimensões NA ORDEM EM QUE FORAM DECLARADAS.

    `report.keywords` é um conjunto sem ordem confiável; a ordem de declaração é
    o que define quem "vence" o agrupamento de um teste multidimensional.
    Também marca se o teste exige navegador — insumo do ledger de estabilidade
    (scripts/estabilidade.py), que só olha para a dimensão browser.
    """
    outcome = yield
    result = outcome.get_result()
    result.webqa_dimensions = [m.name for m in item.iter_markers() if m.name in DIMENSIONS]
    result.webqa_browser = any(m.name == "browser" for m in item.iter_markers())


def pytest_runtest_logreport(report):
    # ERRO de setup/teardown também entra. Antes, só `call` e skip de setup eram
    # registrados — e uma fixture que estourava levava o teste inteiro a
    # DESAPARECER do relatório. Não era perda cosmética: numa execução em que o
    # Chromium não alcançava o alvo, 13 desfechos sumiam, o ledger de
    # estabilidade não achava assinatura de infra nenhuma para classificar e
    # dava a noite como LIMPA — inflando exatamente a métrica que existe para
    # provar que a infraestrutura de navegador funciona.
    interessa = (
        report.when == "call"
        or (report.when == "setup" and (report.skipped or report.failed))
        or (report.when == "teardown" and report.failed)
    )
    if not interessa:
        return
    dims = getattr(report, "webqa_dimensions", None)
    if not dims:  # fallback: sem o hookwrapper (ex.: report sintético)
        dims = [m for m in DIMENSIONS if m in report.keywords]
    # `detail` também para skip: o MOTIVO do skip distingue "sem imagens na
    # página" (resultado legítimo) de "Chromium indisponível" (falha de infra).
    # Sem isso não há como separar flake de veredito — sempre sanitizado.
    detalhe = (
        sanitize_text(str(report.longrepr))[:800]
        if (report.failed or report.skipped)
        else ""
    )
    # `outcome` fica VERBATIM do pytest (o classificador do ledger depende dele).
    # `estado` é a leitura visual: xfail é estado próprio, não um skip qualquer —
    # sem isso o relatório contaria alerta como pulado e perderia a distinção que
    # a dimensão lgpd inteira usa (obrigação × sinal de maturidade).
    # `error` é a terceira distinção: falha FORA do corpo do teste não é veredito
    # sobre o alvo, é o teste não tendo acontecido.
    if report.failed and report.when != "call":
        estado = "error"
    elif hasattr(report, "wasxfail"):
        estado = "xfail"
    else:
        estado = report.outcome
    _RESULTS.append(
        {
            "test": report.nodeid,
            "dimension": dims[0] if dims else "other",
            "dimensions": dims or ["other"],
            "browser": bool(getattr(report, "webqa_browser", "browser" in report.keywords)),
            "outcome": report.outcome,
            "estado": estado,
            # A fase distingue "falhou medindo" de "nem chegou a medir". Um teste
            # pode render duas entradas (call passou, teardown estourou); quem
            # conta desfecho por teste colapsa pelo pior — ver
            # scripts/campanha.py::estados_por_teste.
            "fase": report.when,
            "duration_s": round(getattr(report, "duration", 0.0), 3),
            "detail": detalhe,
        }
    )


def pytest_sessionfinish(session, exitstatus):
    out_dir = report_dir()

    by_dim: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for r in _RESULTS:
        for dim in r.get("dimensions") or [r["dimension"]]:
            by_dim[dim][r["outcome"]] = by_dim[dim].get(r["outcome"], 0) + 1

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.time() - _START, 1),
        "alvo": _alvo_observado(),
        "comando": _comando(session),
        "by_dimension": by_dim,
        "dimension_notes": DIMENSION_NOTES,
        # Medidas do ALVO (webqa/metricas.py), não vereditos: TTFB, total, FCP,
        # LCP, CLS. Ficam só no JSON — o summary.html segue o contrato visual
        # congelado na OS-15, e acrescentar seção ali é iteração de DESIGN, não
        # de instrumentação. Métrica ausente é chave ausente, nunca zero.
        "metricas": coletadas(),
        "results": _RESULTS,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # HTML conforme o pacote de design liberado pelo gate (OS-14): a montagem
    # vive em webqa/report_html.py, testável sem pytest e sem navegador.
    inventario = None
    caminho_terceiros = out_dir / "terceiros.json"
    if caminho_terceiros.exists():
        try:
            inventario = json.loads(caminho_terceiros.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            inventario = None   # inventário ilegível não derruba o relatório

    (out_dir / "summary.html").write_text(
        montar(summary, inventario, _allowlist()), encoding="utf-8"
    )
