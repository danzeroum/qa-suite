"""O layout aguenta outro idioma? (GUI-RESP i18n/RTL, OS-52)

Duas perguntas que nenhum alvo monolíngue responde sozinho, e que só aparecem
quando alguém traduz — quando já é caro:

* **espelhamento** — em árabe ou hebraico a página inteira inverte. Layout preso
  a `margin-left`/`margin-right` em vez de `margin-inline-*` empurra o conteúdo
  para fora da tela, e em LTR não há sintoma nenhum;
* **expansão** — do inglês para o alemão ou o português o texto cresce de 30% a
  100%. Rótulo dimensionado no texto mais curto é cortado no primeiro idioma que
  expandir, e o texto cortado **continua no DOM** — um teste que só olhasse o DOM
  aprovaria.

**Passivo.** As duas manipulações são pseudo-localização no CLIENTE, por
`evaluate`: `dir=rtl` no `<html>` e o texto visível alongado. O alvo não recebe
requisição nova nem formulário — mesma classe do `page.route` da OS-47 —, e nada
persiste: morre com o contexto. O gate C2 (`webqa/gates.py`) segue intocado.

O coletor mora em `webqa/i18n.py` e as decisões (o que expandir, o que conta como
quebra) são puras e testadas sem navegador. Nenhum check fala JS por conta
própria — `scripts/afere_simbolos.py` cobra que todo coletor tenha um check que o
execute, e foi este arquivo que fez aquela guarda ficar verde.
"""
import pytest

from webqa import metricas
from webqa.i18n import (
    FATOR_PADRAO,
    JS_PSEUDO_LOCALIZAR,
    TAGS_QUE_NAO_EXPANDEM,
    quebras_de,
    resumo_de_quebras,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Mesma tolerância do comparador entre engines (OS-48), e pelo mesmo motivo:
# antialiasing e arredondamento de sub-pixel produzem desvios de 1–2px que não
# são defeito. A lição do COMPAT-01 vale aqui em dobro — as violações plantadas
# extravasam por 162px e cortam por 50px, longe da faixa de ruído.
TOLERANCIA_PX = 2


def _sob_manipulacao(contexto_gui, settings, perfis_gui, *, rtl: bool, fator: float):
    """Abre o alvo, estabiliza e devolve o que quebrou sob a manipulação.

    `document.fonts.ready` antes de medir: fonte que chega tarde re-quebra o
    texto e muda a largura, e medir antes é medir uma página que o visitante
    nunca vê (mesma disciplina de `checks/gui/test_reflow.py`).
    """
    pagina = contexto_gui(viewport=perfis_gui["desktop"])
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    pagina.evaluate("() => document.fonts && document.fonts.ready")
    return quebras_de(pagina.evaluate(JS_PSEUDO_LOCALIZAR, {
        "tags": sorted(TAGS_QUE_NAO_EXPANDEM),
        "rtl": rtl, "fator": fator, "tolerancia_px": TOLERANCIA_PX,
    }))


def test_layout_sobrevive_ao_espelhamento_rtl(contexto_gui, settings, perfis_gui):
    """O layout continua dentro da tela quando a direção inverte."""
    quebras = _sob_manipulacao(contexto_gui, settings, perfis_gui, rtl=True, fator=1.0)
    metricas.registrar("gui_rtl_quebrados_n", len(quebras))

    limite = settings.threshold("gui_rtl_quebrados_max")
    assert len(quebras) <= limite, (
        f"{len(quebras)} elemento(s) não sobreviveram ao espelhamento (limite "
        f"{limite:.0f}). Em LTR não há sintoma: a medida foi feita só com "
        f"`dir=rtl` no documento, sem tocar no alvo.\n"
        + resumo_de_quebras(quebras)
        + "\nMargem, padding e posição FÍSICOS (`left`/`right`) não espelham; "
          "os lógicos (`inline-start`/`inline-end`) espelham.")


def test_layout_sobrevive_a_expansao_de_texto(contexto_gui, settings, perfis_gui):
    """O texto traduzido cabe, ou é cortado sem ninguém notar?"""
    quebras = _sob_manipulacao(contexto_gui, settings, perfis_gui,
                               rtl=False, fator=FATOR_PADRAO)
    metricas.registrar("gui_expansao_perdidos_n", len(quebras))

    limite = settings.threshold("gui_expansao_perdidos_max")
    assert len(quebras) <= limite, (
        f"{len(quebras)} elemento(s) não sobreviveram a texto {FATOR_PADRAO:g}× mais "
        f"longo (limite {limite:.0f}) — a faixa de crescimento normal de uma "
        f"tradução.\n" + resumo_de_quebras(quebras)
        + "\nTexto cortado por `overflow:hidden` continua no DOM e não está "
          "disponível para quem lê — é perda, não detalhe de layout.")
