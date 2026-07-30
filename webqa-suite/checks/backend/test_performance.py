"""Performance do backend: TTFB e latência em percentis sob rajada leve.

Percentis, não médias: p95/p99 são onde moram os riscos reais de experiência.
Os limites vêm de config.yaml (orçamentos de performance).
"""
import asyncio

import pytest

from webqa.http_utils import burst, percentiles

pytestmark = pytest.mark.backend


def test_ttfb_dentro_do_orcamento(home_timing, settings):
    limit = settings.threshold("ttfb_ms")
    assert home_timing.ttfb_ms <= limit, (
        f"TTFB {home_timing.ttfb_ms:.0f}ms excede o orçamento de {limit:.0f}ms — "
        "investigue processamento no servidor, filas e cache."
    )


def test_tempo_total_razoavel(home_timing, settings):
    limit = settings.threshold("p95_ms")
    assert home_timing.total_ms <= limit, (
        f"Download completo da home levou {home_timing.total_ms:.0f}ms (> {limit:.0f}ms)."
    )


@pytest.mark.load
def test_latencia_percentis_sob_rajada(settings):
    """Rajada leve e limitada (config: load_burst). Para carga real, use
    loadtest/locustfile.py — este teste é um detector precoce de gargalo.

    Guarda técnica (não só aviso): exige autorização explícita do dono do
    alvo via WEBQA_LOAD_AUTHORIZED=1 — carga sem consentimento pode ser ilegal."""
    import os
    if os.environ.get("WEBQA_LOAD_AUTHORIZED") != "1":
        pytest.skip("Carga requer opt-in explícito: exporte WEBQA_LOAD_AUTHORIZED=1 "
                    "somente com autorização do dono do alvo.")
    latencies = asyncio.run(burst(settings, settings.target_url))
    p = percentiles(latencies)
    assert p["p50"] <= settings.threshold("p50_ms"), f"p50={p['p50']:.0f}ms alto demais"
    assert p["p95"] <= settings.threshold("p95_ms"), f"p95={p['p95']:.0f}ms alto demais"
    assert p["p99"] <= settings.threshold("p99_ms"), f"p99={p['p99']:.0f}ms alto demais"
