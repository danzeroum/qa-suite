"""Renderização real no navegador: Core Web Vitals e erros de JavaScript.

Mede a experiência de fato (design centrado no usuário): FCP, LCP, CLS,
DOMContentLoaded, peso total transferido e console limpo.
Limiares padrão seguem a classificação "bom" do Web Vitals.
"""
import json

import pytest

from webqa.sanitize import sanitize_text

pytestmark = [pytest.mark.frontend, pytest.mark.browser]

VITALS_JS = """
() => new Promise(resolve => {
  const out = {fcp: null, lcp: null, cls: 0, dcl: null};
  const nav = performance.getEntriesByType('navigation')[0];
  if (nav) out.dcl = nav.domContentLoadedEventEnd;
  const paint = performance.getEntriesByType('paint')
      .find(e => e.name === 'first-contentful-paint');
  if (paint) out.fcp = paint.startTime;
  try {
    new PerformanceObserver(l => {
      const e = l.getEntries(); if (e.length) out.lcp = e[e.length-1].startTime;
    }).observe({type: 'largest-contentful-paint', buffered: true});
    new PerformanceObserver(l => {
      for (const e of l.getEntries()) if (!e.hadRecentInput) out.cls += e.value;
    }).observe({type: 'layout-shift', buffered: true});
  } catch (err) {}
  setTimeout(() => resolve(out), 1500);
})
"""


@pytest.fixture(scope="module")
def render(browser_page, settings):
    """Navega uma única vez e coleta métricas + erros de console + peso."""
    errors, total_bytes = [], 0

    browser_page.on("console",
                    lambda m: errors.append(sanitize_text(m.text)[:200]) if m.type == "error" else None)
    browser_page.on("pageerror", lambda e: errors.append(sanitize_text(str(e))[:200]))

    def on_response(resp):
        nonlocal total_bytes
        try:
            total_bytes += len(resp.body())
        except Exception:
            pass

    browser_page.on("response", on_response)
    browser_page.goto(settings.target_url, wait_until="load", timeout=60_000)
    vitals = browser_page.evaluate(VITALS_JS)
    return {"vitals": vitals, "errors": errors, "kb": total_bytes / 1024}


def test_fcp(render, settings):
    fcp = render["vitals"]["fcp"]
    assert fcp is not None, "FCP não medido."
    assert fcp <= settings.threshold("fcp_ms"), f"FCP {fcp:.0f}ms acima do orçamento."


def test_lcp(render, settings):
    lcp = render["vitals"]["lcp"]
    if lcp is None:
        pytest.skip("LCP não reportado pelo navegador nesta página.")
    assert lcp <= settings.threshold("lcp_ms"), (
        f"LCP {lcp:.0f}ms — conteúdo principal demora a aparecer (meta: "
        f"{settings.threshold('lcp_ms'):.0f}ms)."
    )


def test_cls(render, settings):
    cls = render["vitals"]["cls"]
    assert cls <= settings.threshold("cls"), (
        f"CLS {cls:.3f} — a página 'pula' durante o carregamento (meta: {settings.threshold('cls')})."
    )


def test_domcontentloaded(render, settings):
    dcl = render["vitals"]["dcl"]
    assert dcl and dcl <= settings.threshold("dcl_ms"), (
        f"DOMContentLoaded em {dcl and f'{dcl:.0f}'}ms — parsing/JS inicial pesado."
    )


def test_console_sem_erros_js(render, settings):
    limit = settings.threshold("max_console_errors")
    assert len(render["errors"]) <= limit, (
        f"{len(render['errors'])} erros de JS no console:\n"
        + json.dumps(render["errors"][:10], indent=2, ensure_ascii=False)
    )


def test_peso_total_da_pagina(render, settings):
    limit = settings.threshold("page_weight_kb")
    assert render["kb"] <= limit, (
        f"Página transferiu {render['kb']:.0f}KB (> {limit:.0f}KB) — "
        "orçamento de peso estourado."
    )
