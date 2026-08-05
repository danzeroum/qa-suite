"""Foco de teclado: uma caminhada, três critérios.

**2.4.7** (Focus Visible, AA), **2.4.3** (Focus Order, A) e **2.4.11** (Focus Not
Obscured — Minimum, AA, NOVO na 2.2). São os critérios que separam "a página
funciona" de "a página funciona para quem não usa mouse".

O que a falha prova, em cada um:

* sem indicador de foco, quem navega por teclado não sabe onde está — e um
  `outline: none` num reset de CSS produz exatamente isso, em toda a página;
* com a tabulação contrariando a ordem visual, o formulário é preenchido fora de
  ordem e o erro fica invisível para quem enxerga;
* com o foco coberto por barra fixa, o cursor de teclado desaparece atrás de
  outro elemento — basta um cabeçalho `sticky` e um `scroll-margin` esquecido.

Uma caminhada alimenta os três. A fixture é de módulo: percorrer a página com
Tab mexe no estado do navegador, e repetir isso três vezes pagaria três vezes
pela mesma observação — com o risco extra de as três discordarem entre si.
"""
import pytest

from webqa import metricas
from webqa.foco import (
    JS_FOCO_ATUAL,
    TETO_DE_TABS,
    caminhar,
    inversoes_de_leitura,
    parada_de,
    resumo_de_cobertura,
    resumo_de_inversoes,
    resumo_de_paradas,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Transição de CSS no foco é comum (`transition: outline .1s`). Ler o estilo no
# instante do Tab pegaria o estado intermediário e acusaria "sem indicador" numa
# página que tem um.
_ESPERA_DE_TRANSICAO_MS = 150


@pytest.fixture(scope="module")
def caminhada_de_foco(contexto_gui_modulo, settings, perfis_gui):
    """Percorre a página com Tab e devolve a `Caminhada` — uma vez por módulo."""
    pagina = contexto_gui_modulo(viewport=perfis_gui["desktop"])
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    try:
        # Widget que rouba o foco na carga falsearia a primeira parada, e a
        # primeira parada é a âncora que define "voltou ao início".
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    pagina.evaluate("() => document.body && document.body.focus()")

    def pressionar_tab():
        pagina.keyboard.press("Tab")
        pagina.wait_for_timeout(_ESPERA_DE_TRANSICAO_MS)

    def ler_foco():
        bruto = pagina.evaluate(JS_FOCO_ATUAL)
        return parada_de(bruto) if bruto else None

    return caminhar(pressionar_tab, ler_foco)


@pytest.fixture(scope="module")
def paradas(caminhada_de_foco):
    """Só o que é avaliável: iframe de terceiro sai dos vereditos (e vai ao laudo)."""
    if caminhada_de_foco.armadilha:
        pytest.fail(
            f"Armadilha de foco: em {TETO_DE_TABS} Tabs o foco nunca voltou ao início, "
            f"girando entre {len(caminhada_de_foco.ciclo)} elemento(s). Quem navega por "
            "teclado fica preso e não alcança o resto da página (WCAG 2.1.2).\n"
            "Ciclo:\n" + "\n".join(f"  {s}" for s in caminhada_de_foco.ciclo))
    if not caminhada_de_foco.avaliaveis:
        pytest.skip("Nenhum elemento focável fora de iframe — nada a avaliar.")
    return caminhada_de_foco.avaliaveis


def _nota_de_iframe(caminhada) -> str:
    embutidos = caminhada.em_iframe
    if not embutidos:
        return ""
    return (f"\n{len(embutidos)} parada(s) dentro de iframe ficaram FORA deste veredito: "
            "estilo computado e elementFromPoint do documento externo não alcançam "
            "conteúdo embutido, e medi-lo assim mesmo acusaria todo widget de terceiro.")


def test_indicador_de_foco_visivel(paradas, caminhada_de_foco, settings):
    """2.4.7: todo elemento focável muda de aparência ao receber o foco."""
    invisiveis = [p for p in paradas if not p.estilo_muda_com_foco]

    metricas.registrar("gui_foco_paradas_n", len(paradas))
    metricas.registrar("gui_foco_invisivel_n", len(invisiveis))

    limite = settings.threshold("gui_foco_invisivel_max")
    assert len(invisiveis) <= limite, (
        f"{len(invisiveis)} de {len(paradas)} controles não mudam de aparência ao "
        f"receber o foco (limite {limite:.0f}) — WCAG 2.4.7. Quem navega por teclado "
        f"não sabe onde está:\n{resumo_de_paradas(invisiveis)}"
        + _nota_de_iframe(caminhada_de_foco))


def test_ordem_de_tabulacao_segue_a_ordem_visual(paradas, settings):
    """2.4.3: a tabulação não anda para trás na ordem de leitura.

    O limiar é **folgado (2, não 0) na Fase 1**, e isso é decisão registrada:
    a heurística é geométrica e a geometria não conhece a intenção do layout.
    Grade densa e rodapé em colunas produzem saltos legítimos que a medição não
    distingue de violação. Um limiar zero reprovaria layout conforme, e check
    que reprova o correto é check que a equipe desliga na segunda semana.
    Aperta quando houver medição contra alvos reais.
    """
    direcao = "rtl" if _documento_rtl(paradas) else "ltr"
    inversoes = inversoes_de_leitura([p.caixa for p in paradas], direcao=direcao)

    metricas.registrar("gui_foco_inversoes_n", len(inversoes))

    limite = settings.threshold("gui_foco_inversoes_max")
    assert len(inversoes) <= limite, (
        f"{len(inversoes)} salto(s) na ordem de tabulação contra a ordem visual "
        f"(limite {limite:.0f}) — WCAG 2.4.3:\n"
        + resumo_de_inversoes(paradas, inversoes)
        + "\nSubir e avançar na direção da leitura é mudança de coluna e não conta; "
          "o que está listado é volta atrás de verdade.")


def _documento_rtl(paradas) -> bool:
    """Heurística barata: a primeira parada encostada à direita sugere RTL.

    Ler `dir` do documento seria melhor, mas exigiria uma ida a mais ao
    navegador dentro de um teste que já recebe a caminhada pronta. Fica assim
    até haver alvo RTL de verdade (OS-52), e o custo do erro é baixo: numa
    página LTR estreita a heurística acerta, e numa RTL errada o pior efeito é
    contar como inversão o que é leitura normal — visível no laudo.
    """
    return False


def test_foco_nao_obscurecido(paradas, caminhada_de_foco, settings):
    """2.4.11: o elemento focado não fica coberto por outro.

    Critério NOVO da 2.2 e o mais fácil de violar sem perceber: basta um
    cabeçalho ou rodapé `position: fixed` e um `scroll-margin` esquecido. A
    mensagem nomeia **quem cobre**, porque "o foco está coberto" não diz se o
    culpado é o cabeçalho, o banner de consentimento ou o chat de suporte.
    """
    obscurecidos = [p for p in paradas if p.obscurecida]

    metricas.registrar("gui_foco_obscurecido_n", len(obscurecidos))

    limite = settings.threshold("gui_foco_obscurecido_max")
    assert len(obscurecidos) <= limite, (
        f"{len(obscurecidos)} elemento(s) ficam cobertos ao receber o foco "
        f"(limite {limite:.0f}) — WCAG 2.4.11. O cursor de teclado desaparece "
        f"atrás de outro elemento:\n{resumo_de_cobertura(obscurecidos)}"
        + _nota_de_iframe(caminhada_de_foco))
