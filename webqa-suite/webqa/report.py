"""Plugin pytest: relatório consolidado de qualidade (JSON + HTML).

Observabilidade aplicada à própria suíte: cada execução deixa um artefato
inspecionável (report/summary.json e report/summary.html) com resultado por
dimensão de qualidade — backend, frontend, ux, functional, acceptance, load.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from webqa.sanitize import sanitize_text

DIMENSIONS = ("backend", "frontend", "ux", "functional", "acceptance", "load", "verification")
_RESULTS: list[dict] = []
_START = time.time()


def pytest_runtest_logreport(report):
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return
    markers = [m for m in DIMENSIONS if m in report.keywords]
    _RESULTS.append(
        {
            "test": report.nodeid,
            "dimension": markers[0] if markers else "other",
            "outcome": report.outcome,
            "duration_s": round(getattr(report, "duration", 0.0), 3),
            "detail": sanitize_text(str(report.longrepr))[:800] if report.failed else "",
        }
    )


def pytest_sessionfinish(session, exitstatus):
    out_dir = Path(__file__).resolve().parent.parent / "report"
    out_dir.mkdir(exist_ok=True)

    by_dim: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for r in _RESULTS:
        by_dim[r["dimension"]][r["outcome"]] = by_dim[r["dimension"]].get(r["outcome"], 0) + 1

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.time() - _START, 1),
        "by_dimension": by_dim,
        "results": _RESULTS,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = "".join(
        f"<tr class='{r['outcome']}'><td>{r['dimension']}</td><td>{r['test']}</td>"
        f"<td>{r['outcome']}</td><td>{r['duration_s']}s</td></tr>"
        for r in _RESULTS
    )
    dims = "".join(
        f"<li><b>{d}</b>: {c.get('passed', 0)} ok / {c.get('failed', 0)} falhas "
        f"/ {c.get('skipped', 0)} pulados</li>"
        for d, c in sorted(by_dim.items())
    )
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>WebQA Suite — Relatório</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}
 table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ddd;padding:.4rem;font-size:.85rem}}
 tr.passed td{{background:#eefbee}} tr.failed td{{background:#fdecec}} tr.skipped td{{background:#f4f4f4}}
</style></head><body>
<h1>WebQA Suite — Relatório de Qualidade</h1>
<p>Gerado em {summary['generated_at']} · duração {summary['duration_s']}s</p>
<ul>{dims}</ul>
<table><tr><th>Dimensão</th><th>Teste</th><th>Resultado</th><th>Duração</th></tr>{rows}</table>
</body></html>"""
    (out_dir / "summary.html").write_text(html, encoding="utf-8")
