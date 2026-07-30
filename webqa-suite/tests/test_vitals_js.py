"""VERIFICAÇÃO: a coleta de vitals lê as métricas DEPOIS da janela, não em t=0.

Verificação sem navegador: a estrutura do JS é conferida por posição no fonte.
A validação (execução real com Chromium contra a referência de design) fica nos
checks de frontend — este arquivo existe para que a regressão seja barata de
pegar, já que ela é INVISÍVEL: a métrica sai `null` e o teste acusa "não
medido" numa página que pintou em 120ms.
"""
import re

import pytest

from checks.frontend.test_rendering import VITALS_JS

pytestmark = pytest.mark.verification

# Leituras retrospectivas: precisam acontecer depois da janela de observação.
LEITURAS = ("getEntriesByType",)
# Registro de observador: precisa acontecer ANTES, para escutar durante a janela.
OBSERVADORES = ("PerformanceObserver",)


def _limites_da_callback() -> tuple[int, int]:
    """(início, fim) do corpo da callback do setTimeout, por posição no fonte."""
    inicio = VITALS_JS.find("setTimeout(")
    assert inicio > 0, "VITALS_JS precisa resolver dentro de um setTimeout"
    fim = VITALS_JS.find("resolve(out)", inicio)
    assert fim > inicio, "a callback do setTimeout precisa resolver com out"
    return inicio, fim


def test_toda_leitura_de_metrica_ocorre_dentro_da_callback():
    """Regressão do bug: `paint`/`navigation` lidos em t=0 e resolve 1500ms depois."""
    inicio, _ = _limites_da_callback()
    for leitura in LEITURAS:
        fora = [m.start() for m in re.finditer(re.escape(leitura), VITALS_JS) if m.start() < inicio]
        assert not fora, (
            f"'{leitura}' aparece ANTES do setTimeout (posição {fora}) — a janela de "
            "observação não serve de nada se a leitura acontece antes dela."
        )


def test_paint_e_navigation_sao_lidos_apos_a_janela():
    inicio, fim = _limites_da_callback()
    corpo = VITALS_JS[inicio:fim]
    assert "'paint'" in corpo, "leitura de paint precisa estar na callback"
    assert "'navigation'" in corpo, "leitura de navigation precisa estar na callback"
    assert "first-contentful-paint" in corpo


def test_observadores_ficam_registrados_antes_da_janela():
    """LCP e CLS dependem de escutar DURANTE a janela — mover para dentro os cegaria."""
    inicio, _ = _limites_da_callback()
    antes = VITALS_JS[:inicio]
    for observador in OBSERVADORES:
        assert observador in antes, f"{observador} precisa ser registrado antes do setTimeout"
    assert antes.count("buffered: true") == 2, "LCP e CLS precisam de buffered:true"


def test_janela_de_observacao_preservada():
    """Sem mudança de comportamento além do momento da leitura."""
    assert re.search(r"resolve\(out\);\s*\}, 1500\)", VITALS_JS), "janela de 1500ms preservada"


def test_metricas_declaradas_com_null_inicial():
    """Ausência tem de ser distinguível de zero: null, nunca 0."""
    assert re.search(r"fcp:\s*null", VITALS_JS)
    assert re.search(r"lcp:\s*null", VITALS_JS)
    assert re.search(r"dcl:\s*null", VITALS_JS)
    assert re.search(r"cls:\s*0", VITALS_JS), "CLS acumula: começa em 0, não null"
