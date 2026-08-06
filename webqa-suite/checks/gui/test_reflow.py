"""Reflow e ampliação: o conteúdo continua disponível quando a tela encolhe.

WCAG 2.2 **1.4.10 (Reflow)** e **1.4.4 (Resize Text)**, ambos AA. São os dois
critérios que um alvo pode violar passando em tudo o que a suíte media antes:
a home responde 200, o HTML declara `meta viewport`, os Web Vitals estão bons —
e a página é inutilizável num telefone com fonte ampliada.

O que a falha PROVA: a 320 CSS px o visitante precisa rolar em duas direções
para ler uma linha, ou o texto some ao ser ampliado. Nenhuma das duas coisas
depende de contexto, gosto ou público.

Contexto próprio por medição (`contexto_gui`): nada aqui toca `browser_page`,
que é de sessão e alimenta as Web Vitals de `checks/frontend` (R20).
"""
import pytest

from webqa import metricas
from webqa.geometria import (
    JS_INVENTARIO,
    JS_OVERFLOW,
    Caixa,
    perdidos_entre,
    resumo_de_caixas,
)
from webqa.viewports import com_zoom

pytestmark = [pytest.mark.gui, pytest.mark.browser]


def _abrir_e_estabilizar(contexto_gui, settings, viewport):
    """Abre o alvo e espera o que muda largura: rede parada e fontes prontas.

    Fonte que chega tarde re-quebra o texto e muda a largura do conteúdo. Medir
    antes de `document.fonts.ready` é medir uma página que o visitante nunca vê.
    """
    pagina = contexto_gui(viewport=viewport)
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass          # alvo com conexão longa (SSE, websocket) nunca fica ocioso
    pagina.evaluate("() => document.fonts && document.fonts.ready")
    return pagina


def _caixas(brutas) -> list[Caixa]:
    return [Caixa(**b) for b in brutas]


def test_sem_rolagem_horizontal_em_320px(contexto_gui, settings, perfis_gui):
    """1.4.10: a 320 CSS px não pode haver rolagem horizontal.

    320px é o teto da norma — o equivalente a 400% de zoom numa viewport de
    1280 —, não "um celular pequeno" escolhido por gosto.
    """
    pagina = _abrir_e_estabilizar(contexto_gui, settings, perfis_gui["reflow_aa"])
    medida = pagina.evaluate(JS_OVERFLOW)
    extravasantes = _caixas(medida["extravasantes"])

    metricas.registrar("gui_overflow_x_px", medida["overflow"])
    metricas.registrar("gui_extravasantes_n", len(extravasantes))

    limite = settings.threshold("gui_overflow_x_px")
    assert medida["overflow"] <= limite, (
        f"A 320 CSS px a página rola {medida['overflow']:.0f}px na horizontal "
        f"(limite {limite:.0f}px) — WCAG 1.4.10. Ler uma linha passa a exigir "
        f"rolagem em duas direções.\nQuem extravasa ({len(extravasantes)}):\n"
        + resumo_de_caixas(extravasantes))


def test_zoom_200_nao_perde_conteudo(contexto_gui, settings, perfis_gui):
    """1.4.4: a 200% nenhum conteúdo ou função pode deixar de estar disponível.

    Compara dois inventários do que a página oferece, por CONJUNTO de texto
    normalizado. Posições não entram: a 200% tudo se move, e comparar
    coordenadas acusaria a própria ampliação como perda.

    Conteúdo cortado por `overflow: hidden` conta como perdido, e é o caso mais
    comum: ele continua no DOM — logo, um teste que só olhasse o DOM aprovaria —
    e não está disponível para quem lê.
    """
    desktop = perfis_gui["desktop"]
    normal = _abrir_e_estabilizar(contexto_gui, settings, desktop).evaluate(JS_INVENTARIO)
    ampliado = _abrir_e_estabilizar(
        contexto_gui, settings, com_zoom(desktop, 200)).evaluate(JS_INVENTARIO)

    perdas = perdidos_entre(normal, ampliado)
    metricas.registrar("gui_zoom200_perdidos_n", perdas.total)

    limite = settings.threshold("gui_zoom_perdidos_max")
    assert perdas.total <= limite, (
        f"A 200% de zoom {perdas.total} item(ns) deixaram de estar disponíveis "
        f"(limite {limite:.0f}) — WCAG 1.4.4.\n"
        + (f"Marcos que sumiram: {list(perdas.marcos[:5])}\n" if perdas.marcos else "")
        + (f"Textos que sumiram: {list(perdas.textos[:5])}\n" if perdas.textos else "")
        + "Conteúdo cortado por overflow:hidden continua no DOM e não está "
          "disponível para quem lê — é perda, não detalhe de layout.")
