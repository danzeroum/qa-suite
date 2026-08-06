"""VERIFICAÇÃO: caminhada, inversão de leitura e cobertura do foco.

Os três pontos em que este núcleo pode enganar, e por isso os três que os testes
atacam primeiro:

1. **a armadilha tem de virar falha, não travamento.** Um teste que pendura é um
   teste que alguém desliga — e aí a armadilha deixa de ser detectada de vez;
2. **a inversão é heurística.** Subir e ir para a direita é mudança de coluna, e
   um check que a acusasse reprovaria toda grade de duas colunas;
3. **o limiar de cobertura precisa ser exercido na borda.** Um limiar que a
   amostragem não consegue expressar é um limiar que nunca foi testado.

Nada aqui sobe navegador: `caminhar` recebe as ações por parâmetro, como
`percorrer` faz em `webqa/navegacao.py`.
"""
import pytest

from webqa.foco import (
    COBERTURA_MAXIMA,
    TETO_DE_TABS,
    Parada,
    caminhar,
    fracao_coberta_de,
    inversoes_de_leitura,
    parada_de,
)
from webqa.geometria import Caixa

pytestmark = pytest.mark.verification


def _caixa(x=0.0, y=0.0, largura=80.0, altura=20.0, seletor="e"):
    return Caixa(seletor=seletor, x=x, y=y, largura=largura, altura=altura)


def _parada(seletor, x=0.0, y=0.0, **extra):
    return Parada(seletor=seletor, caixa=_caixa(x=x, y=y, seletor=seletor), **extra)


def _passeio(parada_no_passo):
    """Dublê de navegador: `parada_no_passo(i)` devolve a `Parada` do i-ésimo Tab.

    Injetar a função inteira, e não uma lista cíclica, é o que permite modelar a
    armadilha REAL: o foco avança normalmente por alguns elementos e então gruda
    num só. Uma lista cíclica sempre volta ao início, que é justamente o critério
    de término normal — ela não sabe representar "preso".
    """
    estado = {"i": -1}

    def pressionar_tab():
        estado["i"] += 1

    def ler_foco():
        return parada_no_passo(estado["i"])

    return pressionar_tab, ler_foco


def _ciclico(sequencia):
    return lambda i: sequencia[i % len(sequencia)] if sequencia else None


def _gruda_em(prefixo, preso):
    """Anda pelo prefixo e depois nunca mais sai de `preso`."""
    return lambda i: prefixo[i] if i < len(prefixo) else preso


# ---------- Armadilha: falha explicada, nunca travamento ----------

def test_foco_preso_num_elemento_e_armadilha_com_o_ciclo_na_mensagem():
    """O caso do `onblur="this.focus()"`: o foco nunca sai do campo.

    Sem o teto, `caminhar` giraria para sempre e o check morreria por timeout —
    que é indistinguível de infraestrutura quebrada e não diz nada a ninguém.
    """
    tab, ler = _passeio(_gruda_em([_parada("button#antes")], _parada("input#preso")))
    # O inventário é o que torna isto armadilha e não fim de ordem: havia mais
    # coisa focável depois do campo que prende o foco (OS-56).
    focaveis_da_pagina = ["button#antes", "input#preso", "a#depois"]
    caminhada = caminhar(tab, ler, teto=30, focaveis=focaveis_da_pagina)

    assert caminhada.teto_atingido and caminhada.armadilha
    assert caminhada.ciclo == ("input#preso",), "o ciclo tem de nomear onde o foco ficou"


def test_ciclo_curto_entre_poucos_elementos_tambem_e_armadilha():
    """Modal que devolve o foco ao primeiro campo: gira entre três e nunca sai."""
    dentro = [_parada("input#nome"), _parada("button#ok")]
    fora = _parada("a#fora")

    def passo(i):
        return fora if i == 0 else dentro[(i - 1) % len(dentro)]

    # `a#fora` fica inalcançável depois do primeiro Tab: é ele que faz disto
    # armadilha e não fim de ordem (OS-56).
    caminhada = caminhar(*_passeio(passo), teto=40,
                         focaveis=["a#fora", "input#nome", "button#ok", "button#fim"])

    assert caminhada.armadilha
    assert set(caminhada.ciclo) == {"input#nome", "button#ok"}


def test_pagina_comprida_nao_e_confundida_com_armadilha():
    """Teto atingido com muitos elementos DISTINTOS é página longa, não foco preso.

    Reportar isso como armadilha mandaria alguém caçar um defeito inexistente —
    e as duas situações pedem ações opostas de quem lê o laudo.
    """
    tab, ler = _passeio(_ciclico([_parada(f"a#i{i}", y=i * 30) for i in range(1, 60)]))
    caminhada = caminhar(tab, ler, teto=40)

    assert caminhada.teto_atingido
    assert not caminhada.armadilha, "muitos elementos distintos não é armadilha"


def test_voltar_ao_primeiro_encerra_a_caminhada_sem_armadilha():
    sequencia = [_parada("a#um"), _parada("a#dois"), _parada("a#tres")]
    tab, ler = _passeio(_ciclico(sequencia))
    caminhada = caminhar(tab, ler, teto=TETO_DE_TABS)

    assert not caminhada.teto_atingido and not caminhada.armadilha
    assert [p.seletor for p in caminhada.paradas] == ["a#um", "a#dois", "a#tres"]


def test_foco_que_sai_do_documento_encerra_normalmente():
    """`None` é a barra de endereços do navegador — fim natural, não defeito."""
    caminhada = caminhar(lambda: None, lambda: None, teto=10)
    assert caminhada.paradas == () and not caminhada.armadilha


# ---------- 2.4.3: inversões, e o falso positivo de grade ----------

def test_voltar_atras_na_mesma_linha_e_inversao():
    """O caso do fixture: `tabindex` invertendo dois botões lado a lado."""
    caixas = [_caixa(x=200, y=100, seletor="b#cancelar"),
              _caixa(x=100, y=100, seletor="b#comprar")]
    assert inversoes_de_leitura(caixas) == [(0, 1)]


def test_subir_e_ir_para_a_DIREITA_nao_e_inversao():
    """É mudança de coluna — a ordem de leitura esperada num layout em colunas.

    Este é o falso positivo que derruba um check ingênuo: toda grade de duas
    colunas termina a primeira embaixo e começa a segunda em cima.
    """
    caixas = [_caixa(x=0, y=500, seletor="a#fim-da-coluna-1"),
              _caixa(x=400, y=100, seletor="a#topo-da-coluna-2")]
    assert inversoes_de_leitura(caixas) == []


def test_subir_e_ir_para_a_esquerda_e_inversao():
    """Sem avançar na leitura, subir é volta atrás de verdade."""
    caixas = [_caixa(x=400, y=500, seletor="a#depois"),
              _caixa(x=0, y=100, seletor="a#antes")]
    assert inversoes_de_leitura(caixas) == [(0, 1)]


def test_descer_na_pagina_nunca_e_inversao():
    caixas = [_caixa(x=0, y=100), _caixa(x=0, y=200), _caixa(x=0, y=300)]
    assert inversoes_de_leitura(caixas) == []


def test_pequeno_desalinhamento_vertical_nao_conta():
    """Dois controles na mesma linha raramente têm o mesmo `y` exato: um `<input>`
    e um `<button>` diferem por alguns pixels. A tolerância existe para isso."""
    caixas = [_caixa(x=0, y=100), _caixa(x=120, y=103)]
    assert inversoes_de_leitura(caixas) == []


def test_direcao_rtl_espelha_o_criterio():
    """Em RTL a leitura vai da direita para a esquerda: ir para a esquerda é
    avançar, e ir para a DIREITA na mesma linha é que é volta atrás."""
    caixas = [_caixa(x=200, y=100), _caixa(x=100, y=100)]
    assert inversoes_de_leitura(caixas, direcao="rtl") == []

    invertidas = [_caixa(x=100, y=100), _caixa(x=200, y=100)]
    assert inversoes_de_leitura(invertidas, direcao="rtl") == [(0, 1)]


def test_sequencia_de_uma_parada_nao_tem_par():
    assert inversoes_de_leitura([_caixa()]) == []


# ---------- 2.4.11: cobertura na borda ----------

def test_cobertura_de_exatamente_25_por_cento_NAO_reprova():
    """Encostar no limiar é conforme — o `>` é estrito.

    Só é testável porque a amostragem é 4×4: com 3×3, 25% não é representável
    (1/9, 2/9, 3/9), e a borda do limiar nunca seria exercida. Limiar que a
    amostragem não expressa é limiar que nunca foi conferido.
    """
    amostras = [True] * 4 + [False] * 12
    fracao = fracao_coberta_de(amostras)
    assert fracao == pytest.approx(COBERTURA_MAXIMA)
    assert not _parada_com(fracao).obscurecida


def test_um_ponto_a_mais_que_o_limiar_reprova():
    fracao = fracao_coberta_de([True] * 5 + [False] * 11)
    assert _parada_com(fracao).obscurecida


def test_sem_amostra_nao_inventa_cobertura():
    """Ausência de medida não é 100% coberto nem 0% conferido: é 0 e a caixa
    segue avaliável. Inventar cobertura aqui reprovaria alvo conforme."""
    assert fracao_coberta_de([]) == 0.0


def test_totalmente_coberto():
    assert fracao_coberta_de([True] * 16) == 1.0


def _parada_com(fracao):
    return Parada(seletor="x", caixa=_caixa(), fracao_coberta=fracao)


# ---------- 2.4.7: o estilo muda com o foco? ----------

def test_indicador_por_outline_e_reconhecido():
    parada = Parada(seletor="b", caixa=_caixa(),
                    estilo_com_foco={"outline-width": "2px"},
                    estilo_sem_foco={"outline-width": "0px"})
    assert parada.estilo_muda_com_foco


def test_indicador_por_box_shadow_tambem_conta():
    """Reset moderno zera `outline` e devolve o sinal por `box-shadow`. Olhar só
    para `outline` acusaria de inacessível um tema que está correto."""
    parada = Parada(seletor="b", caixa=_caixa(),
                    estilo_com_foco={"box-shadow": "0 0 0 2px blue"},
                    estilo_sem_foco={"box-shadow": "none"})
    assert parada.estilo_muda_com_foco


def test_estilo_identico_e_foco_invisivel():
    igual = {"outline-width": "0px", "box-shadow": "none", "background-color": "rgb(255,255,255)"}
    parada = Parada(seletor="b", caixa=_caixa(), estilo_com_foco=igual, estilo_sem_foco=dict(igual))
    assert not parada.estilo_muda_com_foco


# ---------- Iframe: declarado, nunca ignorado em silêncio ----------

def test_parada_em_iframe_sai_dos_avaliaveis_mas_fica_na_caminhada():
    sequencia = [_parada("a#um"), _parada("iframe#widget", em_iframe=True), _parada("a#dois")]
    tab, ler = _passeio(_ciclico(sequencia))
    caminhada = caminhar(tab, ler, teto=TETO_DE_TABS)

    assert len(caminhada.paradas) == 3
    assert [p.seletor for p in caminhada.avaliaveis] == ["a#um", "a#dois"]
    assert [p.seletor for p in caminhada.em_iframe] == ["iframe#widget"]


# ---------- Conversão do coletor ----------

def test_parada_de_calcula_a_fracao_a_partir_das_amostras():
    bruto = {"seletor": "button#ok", "x": 10, "y": 20, "largura": 80, "altura": 30,
             "estilo_com_foco": {"outline-width": "2px"},
             "estilo_sem_foco": {"outline-width": "0px"},
             "amostras": [True] * 8 + [False] * 8, "cobridor": "div.barra-fixa",
             "em_iframe": False}
    parada = parada_de(bruto)
    assert parada.fracao_coberta == 0.5 and parada.obscurecida
    assert parada.cobridor == "div.barra-fixa", "o laudo precisa nomear QUEM cobre"
    assert parada.caixa.largura == 80 and parada.estilo_muda_com_foco


# ---------- Fim de ordem × armadilha: o discriminador por COBERTURA (OS-56) ----------
#
# As duas situações produzem a MESMA assinatura — teto atingido repetindo poucos
# elementos — e confundi-las custou três `error` no Firefox (run 31044478226).
# A contagem não separa: a armadilha plantada do fixture também repete UM
# elemento. O que separa é se ainda restava alguém por visitar.

def test_estagnar_no_ultimo_com_tudo_visitado_e_FIM_DE_ORDEM():
    """O caso do Firefox: percorreu todos, congelou no último.

    O Chromium dá a volta na ordem de tabulação e o Firefox não — lá o Tab
    passa o foco para a interface do navegador e `document.activeElement` não
    muda mais. Não é defeito do alvo, e tratá-lo como armadilha derrubava os
    três critérios de foco naquela engine com `error`.
    """
    visitados = [_parada("a#um"), _parada("b#dois"), _parada("c#tres")]
    tab, ler = _passeio(_gruda_em(visitados[:-1], visitados[-1]))
    caminhada = caminhar(tab, ler, teto=60,
                         focaveis=["a#um", "b#dois", "c#tres"])
    assert caminhada.teto_atingido
    assert caminhada.fim_de_ordem
    assert not caminhada.armadilha, "fim de ordem não é armadilha"
    assert {p.seletor for p in caminhada.paradas} == {"a#um", "b#dois", "c#tres"}


def test_estagnar_com_focaveis_por_visitar_e_ARMADILHA():
    """A armadilha real: preso antes de alcançar o resto da página."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#dois")))
    caminhada = caminhar(tab, ler, teto=60,
                         focaveis=["a#um", "b#dois", "c#tres", "d#quatro", "e#cinco"])
    assert caminhada.armadilha
    assert not caminhada.fim_de_ordem
    assert caminhada.inalcancados == ("c#tres", "d#quatro", "e#cinco"), (
        "o laudo nomeia quem ficou fora")


def test_sem_inventario_nao_se_afirma_armadilha():
    """Coletor que falhou é ausência de medida, e ausência não vira acusação —
    acusar errado é exatamente o defeito que esta OS conserta."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#dois")))
    caminhada = caminhar(tab, ler, teto=60)
    assert caminhada.teto_atingido
    assert not caminhada.armadilha
    assert not caminhada.fim_de_ordem
    assert not caminhada.inventario_conhecido


def test_inventario_vazio_tambem_nao_acusa():
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#dois")))
    caminhada = caminhar(tab, ler, teto=60, focaveis=[])
    assert not caminhada.armadilha


def test_o_teto_continua_valendo():
    """Sem teto, uma armadilha real trava a suíte em vez de reprovar."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#dois")))
    caminhada = caminhar(tab, ler, teto=30, focaveis=["a#um", "b#dois", "c#tres"])
    assert caminhada.teto_atingido and len(caminhada.paradas) == 30


# ---------- A sonda Shift+Tab: o que a cobertura sozinha não separa ----------
#
# Quando a armadilha está no ÚLTIMO focável — o caso da plantada em
# /gui/estados — não sobra ninguém por visitar, e cobertura descreve os dois
# casos igualmente bem. A validação real pegou isso: o conserto por cobertura,
# sozinho, APAGAVA a detecção da armadilha plantada. A sonda é comportamental.


def _sonda(devolve_o_mesmo: bool):
    """Shift+Tab que devolve o foco ao mesmo elemento (armadilha) ou ao anterior."""
    estado = {"soltou": False}

    def voltar():
        estado["soltou"] = not devolve_o_mesmo
    return voltar, estado


def test_armadilha_no_ULTIMO_focavel_e_pega_pela_sonda():
    """O caso que a cobertura não vê: nada por visitar, e mesmo assim é armadilha."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#preso")))
    caminhada = caminhar(tab, ler, teto=30, focaveis=["a#um", "b#preso"],
                         voltar_tab=lambda: None)
    assert caminhada.armadilha, "Shift+Tab não soltou o foco: está preso"
    assert not caminhada.fim_de_ordem
    assert caminhada.sonda == "armadilha"


def test_fim_de_ordem_e_confirmado_quando_o_foco_SOLTA():
    """O caso do Firefox: Shift+Tab traz o foco de volta ao elemento anterior."""
    passos = [_parada("a#um"), _parada("b#dois"), _parada("c#fim")]
    tab, ler_normal = _passeio(_gruda_em(passos[:-1], passos[-1]))
    soltou = {"sim": False}

    def ler():
        if soltou["sim"]:
            return _parada("b#dois")      # Shift+Tab devolveu ao anterior
        return ler_normal()

    def voltar():
        soltou["sim"] = True

    caminhada = caminhar(tab, ler, teto=30, focaveis=["a#um", "b#dois", "c#fim"],
                         voltar_tab=voltar)
    assert caminhada.fim_de_ordem and not caminhada.armadilha
    assert caminhada.sonda == "fim_de_ordem"


def test_a_sonda_tem_PRIORIDADE_sobre_a_cobertura():
    """Evidência comportamental ganha de inferência. Sem esta ordem, a armadilha
    no fim continuaria invisível mesmo com a sonda implementada."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#preso")))
    # Cobertura diria "fim de ordem" (nada por visitar); a sonda diz o contrário.
    caminhada = caminhar(tab, ler, teto=30, focaveis=["a#um", "b#preso"],
                         voltar_tab=lambda: None)
    assert caminhada.inventario_conhecido and not caminhada.inalcancados
    assert caminhada.armadilha


def test_sem_sonda_a_cobertura_continua_valendo():
    """A sonda é opcional: quem não a injetar continua com o discriminador de
    cobertura, e não perde a armadilha no meio da página."""
    tab, ler = _passeio(_gruda_em([_parada("a#um")], _parada("b#preso")))
    caminhada = caminhar(tab, ler, teto=30, focaveis=["a#um", "b#preso", "c#tres"])
    assert caminhada.armadilha and caminhada.sonda == ""
