"""A pessoa chega onde veio? (GUI-JORN-01/02, OS-51)

Os cenários vivem em `checks/acceptance/features/jornada_usabilidade.feature` e
**não** aqui, de propósito: são os mesmos que o protocolo humano da OS-54 leva
para a sessão moderada. Vocabulário único é o que torna TSR e ToT sintético e
humano comparáveis na mesma régua — duas réguas com o mesmo nome não se
comparam, comparam-se por engano.

**O percurso imita a pessoa, não a topologia.** O robô lê os rótulos e segue o
que parece levar à tarefa; o caminho ótimo (BFS) é a **régua**, nunca o percurso.
A diferença entre os dois é o preço do rótulo ruim, e é o que uma sessão com
usuário mede quando a pessoa vai e volta. Fazer o robô andar pelo ótimo daria
excedente zero sempre e mediria a estrutura do site em vez da sua legibilidade.

**Passivo.** A jornada segue só endereços que a própria aplicação ofereceu no
HTML — a mesma disciplina de `webqa/navegacao.py::percorrer`, e o motivo de a
navegação ser por endereço oferecido e não por `click()`: clique é frágil a
sobreposição e passaria a medir o alvo de toque em vez da rota. Nada submete
formulário, então o gate C2 (`webqa/gates.py`) segue intocado.

**A partição dos vereditos segue a navalha da casa, e é por isso que o TEMPO tem
cenário próprio.** TSR, cliques excedentes e becos são determinísticos contra o
alvo fabricado; ToT é tempo, logo é ambiente. Se o tempo dividisse nodeid com o
resto, o desfecho do conjunto passaria a depender do ambiente — e nenhuma das
medidas determinísticas poderia entrar no contrato 1:1.
"""
import os
import time

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from webqa import metricas
from webqa.jornada import (
    Resultado,
    arestas_com_rotulo,
    avaliar_cliques,
    avaliar_tempo,
    becos,
    caminho_otimo,
    carregar_tarefas,
    escolher_proximo,
    grafo_de,
    motivo_de_nao_chegar,
    reconhece_destino,
    relato_de_becos,
    tarefa_de,
)
from webqa.vitals_interacao import veredito_e_duro

pytestmark = [pytest.mark.gui, pytest.mark.browser]

scenarios("../acceptance/features/jornada_usabilidade.feature")

# Teto de passos da caminhada por rótulo. Existe pelo mesmo motivo do teto da
# caminhada de foco: caminhada sem teto vira laço infinito num alvo que se
# reoferece, e o teto precisa ser MAIOR que qualquer jornada plausível para não
# virar ele próprio o motivo da desistência.
TETO_DE_CLIQUES = 12


@pytest.fixture(scope="module")
def mapa(paginas_internas, settings):
    """O grafo, os textos e os becos — UMA travessia, três perguntas.

    Partilhado pelo módulo pela mesma razão da caminhada de foco: percorrer o
    alvo é a parte cara, e refazê-la por cenário pagaria quatro vezes pela mesma
    observação, com o risco extra de as quatro discordarem num alvo dinâmico.
    """
    if len(paginas_internas) < 2:
        # Uma página só alcançada: ou o alvo é um DOCUMENTO servido direto (a
        # política de privacidade do smoke da OS-44), ou a entrada do site não
        # linka nada. As duas são indistinguíveis daqui, e a diferença entre
        # elas é a diferença entre "não se aplica" e "defeito grave".
        #
        # Skip INSTRUÍDO, no molde do contrato visual da OS-49: jornada precisa de
        # para onde ir, e reprovar um documento único por não ter rota seria falso
        # positivo — que em bateria de usabilidade custa a credibilidade da
        # bateria inteira. Ausência de percurso também não é aprovação: por isso
        # skip, e não passe.
        pytest.skip(
            f"Só {len(paginas_internas)} página alcançada a partir do alvo — não há "
            "jornada a medir. Ou o alvo é um documento servido direto (aponte para a "
            "RAIZ do site para exercer estes cenários), ou a entrada não oferece link "
            "nenhum, e nesse caso o defeito é grave e visível a olho nu.")
    host = settings.target_url.split("//")[-1].split("/")[0]
    grafo = grafo_de(paginas_internas,
                      lambda p: arestas_com_rotulo(p.html, p.url, host))
    return {
        "grafo": grafo,
        "html": {p.url: p.html for p in paginas_internas},
        "entrada": paginas_internas[0].url,
        "becos": becos(grafo, paginas_internas[0].url),
    }


def _caminhar(mapa, tarefa):
    """A caminhada por rótulo, pura sobre o grafo — e o relógio por fora.

    O percurso é decidido pelo grafo (determinístico e testável sem navegador) e
    o TEMPO é medido navegando de verdade pelas páginas escolhidas. Decidir e
    medir na mesma travessia ao vivo faria o percurso depender de o alvo
    responder igual duas vezes.
    """
    destinos = frozenset(u for u, h in mapa["html"].items() if reconhece_destino(tarefa.marco, h))
    atual, percorrido, visitados = mapa["entrada"], [mapa["entrada"]], {mapa["entrada"]}
    parada = ""
    for _ in range(TETO_DE_CLIQUES):
        if atual in destinos:
            parada = ""
            break
        proximo = escolher_proximo(mapa["grafo"].get(atual, ()), tarefa.procura,
                                   frozenset(visitados))
        if proximo is None:
            parada = ("nenhum link desta página tem rótulo que evoque a tarefa — a pessoa "
                      "desiste aqui. Ou o destino não existe, ou existe e ninguém o "
                      "rotulou de um jeito que se ache.")
            break
        atual = proximo
        percorrido.append(atual)
        visitados.add(atual)
    else:
        parada = f"teto de {TETO_DE_CLIQUES} cliques atingido sem chegar."
    return Resultado(
        tarefa=tarefa,
        percorrido=tuple(percorrido),
        otimo=caminho_otimo(mapa["grafo"], mapa["entrada"], destinos),
        parou_em=atual,
        motivo_da_parada=parada,
    )


@pytest.fixture()
def ctx():
    return {}


@given("que o visitante está na página inicial")
def na_pagina_inicial(mapa, ctx):
    ctx["mapa"] = mapa


@given(parsers.parse('que a tarefa é "{nome}"'))
def a_tarefa_e(nome, ctx):
    ctx["tarefa"] = tarefa_de(nome, carregar_tarefas())


@when("ele lê os links de cada página e segue o que parece levar à tarefa")
def segue_os_rotulos(ctx, contexto_gui_modulo, perfis_gui):
    resultado = _caminhar(ctx["mapa"], ctx["tarefa"])
    # O relógio anda sobre a rota escolhida, num contexto próprio: ToT é tempo de
    # TAREFA, e inclui carregar cada página do caminho.
    pagina = contexto_gui_modulo(viewport=perfis_gui["desktop"])
    inicio = time.monotonic()
    for url in resultado.percorrido:
        pagina.goto(url, wait_until="load", timeout=60_000)
    decorrido = (time.monotonic() - inicio) * 1000
    ctx["resultado"] = Resultado(
        tarefa=resultado.tarefa, percorrido=resultado.percorrido, otimo=resultado.otimo,
        tot_ms=decorrido, parou_em=resultado.parou_em,
        motivo_da_parada=resultado.motivo_da_parada)

    # Registro SEMPRE, e antes de qualquer veredito: `pytest.xfail` levanta na
    # hora, e medida registrada depois dele nunca chegaria ao laudo.
    chave = ctx["tarefa"].nome.replace(" ", "_")
    metricas.registrar(f"gui_jornada_tsr_{chave}", ctx["resultado"].tsr)
    metricas.registrar(f"gui_jornada_cliques_{chave}", ctx["resultado"].cliques)
    metricas.registrar(f"gui_jornada_excedente_{chave}", ctx["resultado"].cliques_excedentes)
    metricas.registrar(f"gui_jornada_tot_ms_{chave}", decorrido)


@when("ele percorre as páginas que a aplicação oferece")
def percorre_o_que_e_oferecido(ctx):
    metricas.registrar("gui_jornada_becos_n", len(ctx["mapa"]["becos"]))


@then("ele chega à página da tarefa")
def chega(ctx):
    resultado = ctx["resultado"]
    assert resultado.chegou, motivo_de_nao_chegar(resultado)


@then("não precisa de mais cliques do que a tarefa admite")
def cliques_dentro_do_teto(ctx):
    problemas = avaliar_cliques(ctx["resultado"])
    assert not problemas, "\n".join(problemas)


@then("nenhuma delas o obriga a voltar para continuar")
def sem_becos(ctx):
    encontrados = ctx["mapa"]["becos"]
    assert not encontrados, relato_de_becos(encontrados)


@then("ele conclui dentro do tempo previsto para a tarefa")
def dentro_do_tempo(ctx):
    resultado = ctx["resultado"]
    problemas = avaliar_tempo(resultado)
    medido = (f"Medido: {resultado.tot_ms:.0f}ms em {resultado.cliques} clique(s) "
              f"(orçamento {resultado.tarefa.tot_ms:.0f}ms).")
    detalhe = "\n".join([*(f"  {p}" for p in problemas), medido])

    if problemas and not veredito_e_duro(os.environ.get("WEBQA_ORIGEM")):
        pytest.xfail(
            "Orçamento de tempo de tarefa estourado FORA do ambiente oficial — o número "
            "é ruído provável de máquina compartilhada, não achado sobre o alvo. "
            f"Declare WEBQA_ORIGEM=vps para que isto reprove.\n{detalhe}")
    assert not problemas, (
        f"Tempo de tarefa acima do orçamento no ambiente oficial:\n{detalhe}")
