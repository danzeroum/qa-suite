"""A página responde, ou só termina de pintar?

Core Web Vitals (INP ≤ 200ms é "bom") e ISO 25010 (eficiência de desempenho).

`checks/frontend/test_rendering.py` mede **pintura** (FCP, LCP) e **estabilidade**
(CLS). Nenhuma das três diz se a página estava disponível para responder: um alvo
pode pintar em 400ms, aprovar em todas as vitals de carga, e ficar surdo ao
teclado por mais um segundo enquanto executa o bundle. Este check mede esse
segundo.

O que a falha PROVA: a thread principal ficou presa por tempo somado acima do
orçamento, ou travou mais vezes do que o orçamento admite. Não é opinião sobre
arquitetura nem sobre framework — é tempo de indisponibilidade medido pelo
próprio navegador.

**O veredito é condicionado ao ambiente, e isso está declarado.** TBT oscila por
fatores fora do alvo (runner compartilhado, CPU com governor variável). Afrouxar
o limiar até caber na máquina mais barulhenta esvaziaria a medida; a casa faz o
contrário: a régua fica, e só no ambiente oficial (`WEBQA_ORIGEM=vps`,
`docs/VPS.md`) o estouro reprova. Fora dele é `xfail` com o motivo escrito — e a
medida vai ao laudo dos dois jeitos, porque medida não é veredito.

É também o motivo de este nodeid estar em `fora_do_contrato`: o contrato do alvo
fixture existe para reprovar quando um check para de detectar, e um teste cujo
desfecho depende do ambiente reprovaria por ambiente.
"""
import os

import pytest

from webqa import metricas
from webqa.vitals_interacao import (
    JANELA_PADRAO_MS,
    VITALS_INTERACAO_JS,
    avaliar_orcamento,
    medidas_de,
    motivo_de_inp_ausente,
    resumo_de_tarefas,
    veredito_e_duro,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]


def test_tbt_long_tasks_e_inp(contexto_gui, settings, perfis_gui):
    """GUI-PERF-01: bloqueio da thread principal na carga e numa interação neutra."""
    pagina = contexto_gui(viewport=perfis_gui["desktop"])
    # ANTES do goto, e não depois: `longtask` e `event` são fluxos, não estado
    # consultável. Observer registrado após a carga perde exatamente o período em
    # que uma página pesada trava.
    pagina.add_init_script(VITALS_INTERACAO_JS)
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)

    # Interação NEUTRA: `Tab` move o foco e não navega, não submete e não aciona
    # controle nenhum. Clicar seria sondagem ativa e exigiria
    # WEBQA_ACTIVE_PROBES_AUTHORIZED (webqa/gates.py) — e não é preciso: para
    # medir latência de evento basta um evento.
    pagina.keyboard.press("Tab")
    medidas = medidas_de(
        pagina.evaluate("(ms) => window.__webqa_interacao(ms)", JANELA_PADRAO_MS))

    if not medidas.suporta_longtask:
        pytest.skip(
            "Long Tasks API indisponível nesta engine (só Chromium a implementa) — "
            "TBT e long tasks NÃO foram medidos. Rode a dimensão gui em chromium "
            "para obter o número; engine sem a API não é aprovação.")

    # Registro ANTES de qualquer veredito, e é intencional: `pytest.xfail` levanta
    # na hora, e uma medida registrada depois dele nunca chegaria ao laudo. O
    # aceite desta OS cobra os três números no summary.json mesmo quando o
    # desfecho é xfail — medida e veredito são coisas diferentes.
    metricas.registrar("gui_tbt_ms", medidas.tbt_ms)
    metricas.registrar("gui_long_tasks_n", medidas.long_tasks_n)
    metricas.registrar("gui_inp_ms", medidas.inp_ms)   # None é descartado, não vira 0

    problemas = avaliar_orcamento(
        medidas,
        tbt_max=settings.threshold("gui_tbt_ms"),
        inp_max=settings.threshold("gui_inp_ms"),
        long_tasks_max=settings.threshold("gui_long_tasks_max"),
    )
    relato = "\n".join(f"  {p}" for p in problemas)
    medido = (f"Medido: TBT {medidas.tbt_ms:.0f}ms, {medidas.long_tasks_n} long tasks, "
              f"INP aproximado {'não medido' if medidas.inp_ms is None else f'{medidas.inp_ms:.0f}ms'}"
              f" (janela de {JANELA_PADRAO_MS}ms após um Tab).")
    detalhe = f"{relato}\n{medido}\nTarefas mais caras:\n{resumo_de_tarefas(medidas.tarefas)}"

    # Estouro real vem ANTES da ausência de INP: um alvo que trava 600ms não pode
    # sair do laudo como "não medi a interação". A ausência só decide quando não
    # há nada mais grave a dizer.
    if problemas and not veredito_e_duro(os.environ.get("WEBQA_ORIGEM")):
        pytest.xfail(
            "Orçamento de interatividade estourado FORA do ambiente oficial — o número "
            "é ruído provável de máquina compartilhada, não achado sobre o alvo. "
            f"Declare WEBQA_ORIGEM=vps para que isto reprove.\n{detalhe}")
    assert not problemas, (
        "Interatividade abaixo do orçamento no ambiente oficial — WCAG não cobre "
        f"isto, Core Web Vitals sim:\n{detalhe}")

    if medidas.inp_ms is None:
        # Passar aqui anunciaria cobertura de INP que não houve — o mesmo verde
        # indistinguível do verde legítimo que a pré-checagem de tema escuro
        # existe para impedir (docs/GUI.md §2.2, regra 9).
        pytest.xfail(f"{motivo_de_inp_ausente(medidas)}\n{medido}")
