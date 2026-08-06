"""Tamanho de alvo de toque — WCAG 2.2 **2.5.8 (Target Size, Minimum)**, AA.

Critério NOVO da 2.2, e o mais fácil de violar sem perceber: um ícone de 16px
parece bem no desenho e erra o dedo de quem tem tremor, está no ônibus ou usa a
mão não dominante.

A norma **não** diz "todo alvo tem 24px" — ela perdoa o alvo pequeno quando cai
uma exceção. O algoritmo das exceções vive em `webqa/geometria.py`, decomposto e
testado sobre caixas fabricadas; aqui só se mede e se relata. Ignorá-las
reprovaria em massa qualquer página com link dentro de texto, e falso positivo
em bateria de acessibilidade custa a credibilidade da bateria inteira.

Duas fronteiras que o check declara em vez de esconder:

* **24 é norma, 44 é meta de plataforma.** Alvo entre os dois vira ALERTA, nunca
  achado — cobrar norma que não existe desgasta tanto quanto deixar de cobrar a
  que existe;
* **as exceções *user agent control* e *essential* não são observáveis.** Um
  alvo pequeno por exigência legal aparecerá como ofensor e precisa de decisão
  humana. Limite declarado, não esquecimento.
"""
import pytest

from webqa import metricas
from webqa.geometria import (
    JS_ALVOS_DE_TOQUE,
    Caixa,
    classificar_alvos,
    resumo_de_caixas,
    resumo_de_isentos,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Rolagem em passos de uma viewport, com teto: conteúdo preguiçoso só existe
# depois de entrar em cena, e alvo não renderizado é NÃO AVALIADO — nunca
# aprovado. O teto evita que rolagem infinita transforme o check em laço.
_PASSOS_DE_ROLAGEM = 12


def _rolar_a_pagina_inteira(pagina) -> None:
    pagina.evaluate(
        """async (passos) => {
             const alturaDaTela = window.innerHeight;
             for (let i = 0; i < passos; i++) {
               window.scrollTo(0, alturaDaTela * (i + 1));
               await new Promise(r => setTimeout(r, 120));
               if (window.scrollY + alturaDaTela >= document.body.scrollHeight - 1) { break; }
             }
             window.scrollTo(0, 0);
             await new Promise(r => setTimeout(r, 120));
           }""",
        _PASSOS_DE_ROLAGEM)


def test_area_minima_de_toque(contexto_gui, settings, perfis_gui):
    """Todo alvo interativo tem 24×24 CSS px, ou cai numa exceção da norma."""
    pagina = contexto_gui(viewport=perfis_gui["mobile"])
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    pagina.evaluate("() => document.fonts && document.fonts.ready")
    _rolar_a_pagina_inteira(pagina)

    caixas = [Caixa(**b) for b in pagina.evaluate(JS_ALVOS_DE_TOQUE)]
    if not caixas:
        pytest.skip("Nenhum elemento interativo visível na home — nada a medir.")

    minimo = settings.threshold("gui_alvo_toque_px")
    meta = settings.threshold("gui_alvo_toque_meta_px")
    laudo = classificar_alvos(caixas, minimo=minimo, meta=meta)

    # Registradas passem ou falhem os asserts: `menor` é `None` quando não houve
    # alvo, e ausência de medida não é alvo de 0px.
    metricas.registrar("gui_alvo_menor_px", laudo.menor)
    metricas.registrar("gui_alvo_abaixo_min_n", len(laudo.ofensores))
    metricas.registrar("gui_alvo_abaixo_meta_n", len(laudo.alertas))

    if not laudo.ofensores and laudo.alertas:
        pytest.xfail(
            f"{len(laudo.alertas)} alvo(s) entre {minimo:.0f} e {meta:.0f}px: atendem à "
            f"WCAG 2.5.8 e ficam abaixo da meta das plataformas.\n"
            + resumo_de_caixas(list(laudo.alertas)))

    assert not laudo.ofensores, (
        f"{len(laudo.ofensores)} alvo(s) de toque abaixo de {minimo:.0f}x{minimo:.0f} CSS px "
        f"sem exceção aplicável (WCAG 2.5.8):\n"
        + resumo_de_caixas(list(laudo.ofensores))
        + (f"\nIsentos pela norma ({len(laudo.isentos)}):\n" + resumo_de_isentos(laudo.isentos)
           if laudo.isentos else "")
        + "\nAs exceções conferidas são inline, equivalente e espaçamento. "
          "'user agent control' e 'essential' não são observáveis de fora e "
          "exigem decisão humana.")
