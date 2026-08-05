"""Preferências declaradas pela pessoa — a interface as respeita?

WCAG 2.2 **2.3.3 (Animation from Interactions)**. `prefers-reduced-motion:
reduce` não é gosto: quem o liga costuma ter distúrbio vestibular, e movimento
não suprimido produz náusea e tontura de verdade.

O que a falha PROVA: o alvo recebeu a declaração do sistema operacional e
animou assim mesmo. Não depende de contexto, público ou opinião — a pessoa
pediu, e a página não atendeu.

A decisão que faz este check valer alguma coisa é o **filtro**, e ele vive em
`webqa/movimento.py`: contar toda animação acusaria de violação todo alvo que
anima na entrada e para, que é justamente o que se espera de uma página
bem-feita.
"""
import pytest

from webqa import metricas
from webqa.movimento import JS_ANIMACOES, animacoes_persistentes, resumo_de_animacoes

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Janela de observação. A animação de entrada é o falso positivo óbvio: ela roda
# durante a carga e termina. Medir em `networkidle` ainda a pegaria no ar; mais
# um segundo a deixa acabar. É a mesma disciplina do `VITALS_JS`, que observa
# DEPOIS da janela em vez de no instante do load.
_JANELA_APOS_OCIOSO_MS = 1000


def test_reduced_motion_respeitado(contexto_gui, settings, perfis_gui):
    """2.3.3: sob `reduced-motion: reduce`, nada continua se mexendo."""
    pagina = contexto_gui(viewport=perfis_gui["desktop"], reduced_motion="reduce")
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass          # alvo com conexão longa (SSE, websocket) nunca fica ocioso
    pagina.wait_for_timeout(_JANELA_APOS_OCIOSO_MS)

    persistentes = animacoes_persistentes(pagina.evaluate(JS_ANIMACOES))
    metricas.registrar("gui_animacoes_sob_rm_n", len(persistentes))

    limite = settings.threshold("gui_animacoes_sob_rm_max")
    assert len(persistentes) <= limite, (
        f"{len(persistentes)} animação(ões) seguem rodando com "
        f"prefers-reduced-motion: reduce (limite {limite:.0f}) — WCAG 2.3.3. "
        "A pessoa declarou que movimento a incomoda, e a página animou assim "
        f"mesmo:\n{resumo_de_animacoes(persistentes)}\n"
        "Só entram aqui animações ATIVAS e infinitas ou com mais de 1s pela "
        "frente — animação de entrada que termina não conta.")
