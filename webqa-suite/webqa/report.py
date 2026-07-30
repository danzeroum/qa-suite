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
import time
from collections import defaultdict
from pathlib import Path

import pytest

from webqa.sanitize import sanitize_text

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

REPORT_DIR = Path(__file__).resolve().parent.parent / "report"
_RESULTS: list[dict] = []
_START = time.time()


def report_dir() -> Path:
    """Diretório de artefatos, criado sob demanda (usado também pelos checks)."""
    REPORT_DIR.mkdir(exist_ok=True)
    return REPORT_DIR


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Anexa ao report as dimensões NA ORDEM EM QUE FORAM DECLARADAS.

    `report.keywords` é um conjunto sem ordem confiável; a ordem de declaração é
    o que define quem "vence" o agrupamento de um teste multidimensional.
    """
    outcome = yield
    result = outcome.get_result()
    result.webqa_dimensions = [m.name for m in item.iter_markers() if m.name in DIMENSIONS]


def pytest_runtest_logreport(report):
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    dims = getattr(report, "webqa_dimensions", None)
    if not dims:  # fallback: sem o hookwrapper (ex.: report sintético)
        dims = [m for m in DIMENSIONS if m in report.keywords]
    _RESULTS.append(
        {
            "test": report.nodeid,
            "dimension": dims[0] if dims else "other",
            "dimensions": dims or ["other"],
            "outcome": report.outcome,
            "duration_s": round(getattr(report, "duration", 0.0), 3),
            "detail": sanitize_text(str(report.longrepr))[:800] if report.failed else "",
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
        "by_dimension": by_dim,
        "dimension_notes": DIMENSION_NOTES,
        "results": _RESULTS,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = "".join(
        f"<tr class='{r['outcome']}'><td>{' + '.join(r.get('dimensions') or [r['dimension']])}</td>"
        f"<td>{r['test']}</td>"
        f"<td>{r['outcome']}</td><td>{r['duration_s']}s</td></tr>"
        for r in _RESULTS
    )
    dims = "".join(
        f"<li><b>{d}</b>: {c.get('passed', 0)} ok / {c.get('failed', 0)} falhas "
        f"/ {c.get('skipped', 0)} pulados"
        + (f"<p class='nota'>{DIMENSION_NOTES[d]}</p>" if d in DIMENSION_NOTES else "")
        + "</li>"
        for d, c in sorted(by_dim.items())
    )
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>WebQA Suite — Relatório</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}
 table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:.4rem;font-size:.85rem}}
 tr.passed td{{background:#eefbee}} tr.failed td{{background:#fdecec}} tr.skipped td{{background:#f4f4f4}}
 p.nota{{margin:.2rem 0 .6rem;padding:.4rem .6rem;border-left:3px solid #b58900;
        background:#fffbe6;font-size:.8rem;color:#555;max-width:70ch}}
</style></head><body>
<h1>WebQA Suite — Relatório de Qualidade</h1>
<p>Gerado em {summary['generated_at']} · duração {summary['duration_s']}s</p>
<p style="font-size:.8rem;color:#666">Um teste pode contar em mais de uma dimensão
(ex.: acessibilidade é <b>ux</b> e <b>lgpd</b> — LBI Art. 63); o agrupamento usa a
primeira dimensão declarada.</p>
<ul>{dims}</ul>
<table><tr><th>Dimensão</th><th>Teste</th><th>Resultado</th><th>Duração</th></tr>{rows}</table>
</body></html>"""
    (out_dir / "summary.html").write_text(html, encoding="utf-8")
