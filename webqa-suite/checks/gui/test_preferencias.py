"""Preferências declaradas pela pessoa — a interface as respeita?

Duas preferências que o sistema operacional informa e a página pode honrar ou
ignorar: **2.3.3** (movimento) e **1.4.3** medido no tema escuro (contraste).

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
from webqa.axe import baixar_axe_verificado, resumo_de_violacoes, violacoes_por_impacto
from webqa.i18n import (
    JS_DISTINTIVOS,
    distintivos_de,
    informacao_perdida,
    relato_de_perdas,
)
from webqa.movimento import JS_ANIMACOES, animacoes_persistentes, resumo_de_animacoes
from webqa.tema import JS_FUNDO_DO_BODY, implementa_tema_escuro, motivo_de_pular

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Janela de observação. A animação de entrada é o falso positivo óbvio: ela roda
# durante a carga e termina. Medir em `networkidle` ainda a pegaria no ar; mais
# um segundo a deixa acabar. É a mesma disciplina do `VITALS_JS`, que observa
# DEPOIS da janela em vez de no instante do load.
_JANELA_APOS_OCIOSO_MS = 1000

# Alvo que alterna tema por JavaScript o faz depois do load.
_ESPERA_DE_TEMA_MS = 400


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


def test_contraste_em_tema_escuro(contexto_gui, settings, perfis_gui, client):
    """1.4.3: texto sobre fundo com contraste suficiente TAMBÉM no tema escuro.

    **Complementa, não repete** `checks/ux/test_acessibilidade.py`: aquele roda
    o axe uma vez, no tema que o navegador trouxer — na prática, o claro. Uma
    régua, dois temas: os limiares são os MESMOS (`a11y_critical_max` e
    `a11y_serious_max`), porque contraste insuficiente é insuficiente em
    qualquer esquema de cor.

    A pré-checagem não é cortesia. Num alvo sem tema escuro o navegador
    renderiza o claro de novo, o axe não acha nada novo e o teste passa
    anunciando cobertura de um tema que nunca foi medido — o verde
    indistinguível do verde legítimo (`docs/GUI.md §2.2`, regra 9).
    """
    fundo_claro = contexto_gui(color_scheme="light").evaluate(JS_FUNDO_DO_BODY)

    pagina = contexto_gui(viewport=perfis_gui["desktop"], color_scheme="dark")
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    # Alternância de tema por JavaScript acontece DEPOIS do load em boa parte
    # dos alvos; ler no instante do networkidle pegaria o estado anterior.
    pagina.wait_for_timeout(_ESPERA_DE_TEMA_MS)

    fundo_escuro = pagina.evaluate(JS_FUNDO_DO_BODY)
    if not implementa_tema_escuro(fundo_claro, fundo_escuro):
        pytest.skip(motivo_de_pular(fundo_escuro))

    try:
        axe_js = baixar_axe_verificado(client)
    except AssertionError:
        raise                 # hash divergente é comprometimento, nunca "não medi"
    except Exception as exc:
        pytest.skip(f"Não foi possível baixar o axe-core ({exc}).")
    pagina.add_script_tag(content=axe_js)
    resultado = pagina.evaluate(
        "async () => await axe.run(document, {runOnly: ['color-contrast']})")

    serias = violacoes_por_impacto(resultado, "serious")
    criticas = violacoes_por_impacto(resultado, "critical")
    metricas.registrar("gui_contraste_violacoes_dark_n", len(serias) + len(criticas))

    limite = settings.threshold("a11y_serious_max")
    assert len(serias) + len(criticas) <= limite, (
        f"{len(serias) + len(criticas)} violação(ões) de contraste no TEMA ESCURO "
        f"(limite {limite:.0f}) — WCAG 1.4.3. O tema claro é medido por "
        f"checks/ux/test_acessibilidade.py; este mede o outro:\n"
        + resumo_de_violacoes(serias + criticas)
        + f"\nFundo do body: {fundo_claro} no claro, {fundo_escuro} no escuro.")


def test_forced_colors_nao_apaga_informacao(contexto_gui, settings, perfis_gui):
    """GUI-CONTR-03: no modo de alto contraste, o que era só cor continua legível.

    O modo de cores forçadas substitui a paleta do autor pela do sistema. Isso é
    o RECURSO, não o defeito — quem o liga quer exatamente isso. O defeito é
    outro: um elemento que se distinguia dos vizinhos **só** por fundo ou borda e
    que, sob a substituição, passa a ser indistinguível deles. A informação que a
    cor carregava não foi substituída por nada.

    **Mudar de cor não é perder informação.** Acusar mudança de cor acusaria o
    recurso, e o laudo viraria uma lista do que o modo faz de propósito. Por isso
    o comparador isenta quem tem texto próprio (o texto atravessa) e quem tem
    borda que sobrevive — o caso do `.campo-erro` do alvo fabricado, cuja borda
    permanece `solid` e só troca de cor.

    A capacidade é perguntada ao NAVEGADOR, nunca a uma lista de engines
    (lição das OS-46/56): se a media query não acompanhar a emulação, a
    comparação não mediria nada e o check pula nomeando a incapacidade — verde
    permanente é o que `tests/test_i18n.py` fixa como proibido.
    """
    def colher(forcado: bool):
        pagina = contexto_gui(viewport=perfis_gui["desktop"])
        if forcado:
            pagina.emulate_media(forced_colors="active")
        pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
        pagina.evaluate("() => document.fonts && document.fonts.ready")
        return pagina, pagina.evaluate(JS_DISTINTIVOS)

    pagina_forcada, forcado = colher(True)
    if not pagina_forcada.evaluate("() => matchMedia('(forced-colors: active)').matches"):
        pytest.skip(
            "Esta engine não aplicou `forced-colors: active` — a media query não "
            "acompanhou a emulação, então comparar estilo computado entre os dois "
            "modos não mediria nada. Rode a dimensão gui em chromium para obter o "
            "veredito; engine sem o modo não é aprovação.")
    _, normal = colher(False)

    perdidos = informacao_perdida(distintivos_de(normal, forcado))
    metricas.registrar("gui_fc_informacao_perdida_n", len(perdidos))

    limite = settings.threshold("gui_fc_informacao_perdida_max")
    assert len(perdidos) <= limite, (
        f"{len(perdidos)} elemento(s) perderam sob forced-colors o ÚNICO distintivo "
        f"que tinham (limite {limite:.0f}) — WCAG 1.4.1 pelo avesso: a cor era o "
        f"portador único, e o modo de alto contraste a substituiu.\n"
        + relato_de_perdas(perdidos[:10]))
