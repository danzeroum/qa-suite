"""VERIFICAÇÃO da seleção de engine de navegador (compatibilidade multi-engine, C3).

Sem rede e sem navegador: `engines_configurados` é pura, decide a matriz a partir
do env. O skip honesto por engine ausente é exercitado pelo fixture `browser`
contra o alvo real (a dimensão browser), não aqui — regra §2.11.
"""
from __future__ import annotations

import pytest

from webqa.navegador import ENGINE_PADRAO, ENGINES_VALIDAS, engines_configurados

pytestmark = pytest.mark.verification


def test_default_e_so_chromium_para_nao_triplicar_o_ci():
    """Sem WEBQA_BROWSER_ENGINES, o PR roda só chromium (R-Q5)."""
    assert engines_configurados({}) == (ENGINE_PADRAO,)
    assert engines_configurados({"WEBQA_BROWSER_ENGINES": ""}) == (ENGINE_PADRAO,)
    assert engines_configurados({"WEBQA_BROWSER_ENGINES": "  "}) == (ENGINE_PADRAO,)


def test_matriz_completa_declarada_no_env():
    assert engines_configurados(
        {"WEBQA_BROWSER_ENGINES": "chromium,firefox,webkit"}
    ) == ("chromium", "firefox", "webkit")


def test_ordem_preservada_e_duplicatas_removidas():
    assert engines_configurados(
        {"WEBQA_BROWSER_ENGINES": "webkit, chromium, webkit"}
    ) == ("webkit", "chromium")


def test_tolera_espaco_e_maiuscula():
    assert engines_configurados(
        {"WEBQA_BROWSER_ENGINES": " Firefox , CHROMIUM "}
    ) == ("firefox", "chromium")


def test_engine_desconhecida_e_erro_nao_filtro_silencioso():
    """Fail-closed: um typo não pode virar 'rodou zero engines e passou'."""
    with pytest.raises(ValueError, match="chromiun"):
        engines_configurados({"WEBQA_BROWSER_ENGINES": "chromiun"})
    # E mesmo misturada com engines válidas, a inválida derruba a seleção inteira.
    with pytest.raises(ValueError, match="opera"):
        engines_configurados({"WEBQA_BROWSER_ENGINES": "chromium,opera"})


def test_todas_as_engines_validas_sao_aceitas():
    for engine in ENGINES_VALIDAS:
        assert engines_configurados({"WEBQA_BROWSER_ENGINES": engine}) == (engine,)
