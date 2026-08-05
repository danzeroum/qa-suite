"""O layout aguenta a matriz de viewports, ou só o do desenvolvedor?

Três perguntas que só existem quando a largura muda:

* **GUI-RESP-03** — controles que se cobrem. Sobreposição não é feiura: o
  controle coberto simplesmente não é clicável, e quem desenhou não vê porque no
  monitor dele os dois cabem lado a lado;
* **GUI-RESP-04** — CLS **por viewport**. `checks/frontend/test_rendering.py`
  mede CLS uma vez, no viewport que o navegador trouxer. Layout que salta é um
  defeito de largura estreita muito mais que de largura larga, e medir só a larga
  é medir onde o defeito não mora;
* **GUI-RESP-05** — a navegação principal em tela estreita. O "e" do critério é
  tudo: abre por clique **e** por teclado.

**A iteração de viewport acontece DENTRO do corpo**, e não por `parametrize`.
Convenção da casa desde a OS-42: o contrato do alvo fixture é por nodeid exato, e
`::test_x[mobile]` deixa de existir quando alguém reordena a matriz — o contrato
passaria a cobrar um id fantasma. O laudo perde a granularidade por viewport no
nodeid e a recupera na mensagem, que nomeia o viewport de cada achado.

**Firefox e a pendência da OS-41.** `is_mobile`/`has_touch` são rejeitados pelo
Firefox, então o perfil móvel roda lá como **largura sem emulação**. Estes três
checks julgam por LARGURA, então rodam em qualquer engine — e a nota da
não-emulação acompanha o laudo. Check cujo veredito dependesse da emulação (e não
da largura) trataria o Firefox como skip pontual; nenhum destes é o caso, e a
diferença está declarada aqui porque um laudo que não a declara mente por omissão.
"""
import pytest

from webqa import metricas
from webqa.geometria import (
    JS_INTERATIVOS,
    interativos_de,
    resumo_de_sobreposicoes,
    sobreposicoes,
)
from webqa.menu import (
    JS_FOCAVEL,
    JS_GATILHOS,
    JS_NAV,
    gatilho_de,
    motivo_de_abrandar,
    motivo_de_reprovar,
)
from webqa.viewports import viewports_configurados

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# O CLS de `VITALS_JS` é observado numa janela; reusar o módulo irmão em vez de
# reescrever a observação é o que garante que os dois números sejam comparáveis.
_JANELA_DE_CLS_MS = 1_500

# Espera entre acionar o gatilho e ler a navegação: menu costuma abrir com
# transição, e ler no instante do clique pegaria o estado intermediário.
_ESPERA_DE_MENU_MS = 400


def _nota_de_engine(pagina) -> str:
    """A diferença do Firefox, escrita no laudo em vez de escondida na fixture."""
    if "firefox" not in (pagina.context.browser.browser_type.name or ""):
        return ""
    return ("\nNota: no Firefox o perfil móvel roda como LARGURA sem emulação "
            "(`is_mobile`/`has_touch` são recusados pela engine). O veredito acima é "
            "de largura, então vale; o que NÃO foi exercido é o comportamento de toque.")


def test_sem_sobreposicao_de_interativos(contexto_gui, settings, perfis_gui):
    """GUI-RESP-03: nenhum par de controles divide área em nenhum viewport.

    Pares ancestral-descendente são EXCLUÍDOS: um `<a>` dentro de um `<nav>`
    clicável cobre 100% de si mesmo dentro do pai, e chamar isso de sobreposição
    acusaria de defeito o aninhamento normal de qualquer menu. A exclusão é
    estrutural e vem do navegador (`contains`), não de adivinhação sobre seletores.
    """
    limite = settings.threshold("gui_sobreposicao_fracao")
    achados_por_viewport = {}
    for viewport in viewports_configurados(perfis=perfis_gui):
        pagina = contexto_gui(viewport=viewport)
        pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
        achados = sobreposicoes(interativos_de(pagina.evaluate(JS_INTERATIVOS)),
                                limite=limite)
        metricas.registrar(f"gui_sobreposicoes_{viewport.nome}_n", len(achados))
        if achados:
            achados_por_viewport[viewport] = (achados, pagina)

    total = sum(len(a) for a, _ in achados_por_viewport.values())
    teto = settings.threshold("gui_sobreposicao_max")
    assert total <= teto, (
        f"{total} par(es) de controles se sobrepõem além de {limite * 100:.0f}% da menor "
        f"caixa (limite {teto:.0f}). O controle coberto não é clicável, e quem desenhou "
        "não vê porque no monitor dele os dois cabem lado a lado:\n"
        + "\n".join(f"  [{viewport.nome} {viewport.largura}px]\n"
                    + resumo_de_sobreposicoes(achados) + _nota_de_engine(pagina)
                    for viewport, (achados, pagina) in achados_por_viewport.items()))


def test_cls_por_viewport(contexto_gui, settings, perfis_gui):
    """GUI-RESP-04: o layout não salta em nenhuma largura da matriz.

    Mesma régua do CLS de `checks/frontend/test_rendering.py` (`thresholds.cls`),
    de propósito: "salta" é salta em qualquer largura, e um limiar próprio aqui
    faria dois números com o mesmo nome significarem coisas diferentes no laudo.
    O que muda não é a régua, é onde ela é aplicada.
    """
    from checks.frontend.test_rendering import VITALS_JS

    medidos, estourados = {}, []
    limite = settings.threshold("cls")
    for viewport in viewports_configurados(perfis=perfis_gui):
        pagina = contexto_gui(viewport=viewport)
        pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
        cls = (pagina.evaluate(VITALS_JS) or {}).get("cls")
        # Registrada MESMO quando passa: é o número que permite comparar
        # execuções e ver a tendência antes de o orçamento estourar.
        metricas.registrar(f"gui_cls_{viewport.nome}", cls)
        if cls is None:
            continue                  # ausência de medida não é estabilidade
        medidos[viewport.nome] = cls
        if cls > limite:
            estourados.append(f"  {viewport.nome} ({viewport.largura}px): CLS {cls:.3f}")

    if not medidos:
        pytest.skip("Nenhum viewport reportou CLS — o navegador não emitiu "
                    "`layout-shift` em nenhuma largura. Ausência de medida, não estabilidade.")
    assert not estourados, (
        f"O layout salta durante a carga em {len(estourados)} viewport(s) "
        f"(limite {limite}) — o visitante clica onde o botão estava, não onde ele "
        "ficou:\n" + "\n".join(estourados)
        + f"\nMedido em todos: {medidos}")


def test_navegacao_principal_utilizavel_em_mobile(contexto_gui, settings, perfis_gui):
    """GUI-RESP-05: em tela estreita a navegação está visível, ou abre por clique
    **e** por teclado.

    O "e" é o critério inteiro. Menu que abre com o dedo e não com o teclado não
    está meio acessível: para quem navega por teclado, a navegação do site não
    existe (WCAG 2.1.1).

    Clicar aqui é passivo — o gate de sondagem ativa existe contra o que ESCREVE
    no alvo (`webqa/gates.py`), e abrir um menu não escreve nada. Ainda assim
    `a[href]` e `[type=submit]` são excluídos no coletor, e o check abandona a
    medição se a URL mudar: menu que navega não é menu.
    """
    estreitos = [v for v in viewports_configurados(perfis=perfis_gui) if v.largura <= 700]
    if not estreitos:
        pytest.skip("Nenhum viewport estreito na seleção (WEBQA_VIEWPORTS) — este "
                    "check só tem pergunta a fazer abaixo de 700px.")

    reprovas, abrandar = [], []
    for viewport in estreitos:
        pagina = contexto_gui(viewport=viewport)
        pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
        nav = pagina.evaluate(JS_NAV)
        if nav["visivel"]:
            continue                  # visível já é utilizável: não há gatilho a exigir
        gatilho = _medir_gatilho(pagina, settings)
        motivo = motivo_de_reprovar(gatilho)
        rotulo = f"[{viewport.nome} {viewport.largura}px]"
        if motivo:
            reprovas.append(f"  {rotulo} {motivo}{_nota_de_engine(pagina)}")
        elif not (nav["seletor"] and gatilho.abre_por_teclado):
            abrandar.append(f"  {rotulo} {motivo_de_abrandar(gatilho, nav['seletor'] or 'nenhuma')}")

    assert not reprovas, (
        "A navegação principal não é operável por teclado em tela estreita "
        f"({len(reprovas)} viewport(s)):\n" + "\n".join(reprovas))
    if abrandar:
        pytest.xfail("Navegação principal não confirmada em tela estreita:\n"
                     + "\n".join(abrandar))


def _medir_gatilho(pagina, settings):
    """Aciona o candidato de duas formas e devolve o que cada uma produziu.

    Duas cargas, e não uma: o clique deixa o menu ABERTO, e testar o teclado
    depois disso responderia "sim" para qualquer gatilho — o menu já estaria
    visível antes de a tecla ser pressionada. Cada acionamento precisa de um
    estado inicial limpo, e é por isso que a página é recarregada entre eles.
    """
    candidatos = pagina.evaluate(JS_GATILHOS)
    if not candidatos:
        return gatilho_de({})
    seletor = candidatos[0]

    focavel = bool(pagina.evaluate(JS_FOCAVEL, seletor))
    por_teclado = False
    if focavel:
        for tecla in ("Enter", " "):
            pagina.keyboard.press(tecla)
            pagina.wait_for_timeout(_ESPERA_DE_MENU_MS)
            if pagina.evaluate(JS_NAV)["visivel"]:
                por_teclado = True
                break

    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    antes = pagina.url
    pagina.click(seletor, timeout=5_000)
    pagina.wait_for_timeout(_ESPERA_DE_MENU_MS)
    navegou = pagina.url != antes
    por_clique = (not navegou) and pagina.evaluate(JS_NAV)["visivel"]
    return gatilho_de({"seletor": seletor, "focavel": focavel, "navegou": navegou,
                       "abre_por_clique": por_clique, "abre_por_teclado": por_teclado})
