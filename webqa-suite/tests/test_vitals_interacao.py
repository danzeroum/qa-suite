"""VERIFICAÇÃO: a aritmética do TBT e a disciplina de observers do coletor.

Dois blocos, e cada um cobre um defeito que não deixa marca:

* **a aritmética** — TBT somado errado sai como um número plausível. Ninguém
  desconfia de "TBT 410ms"; o teste é a única coisa que separa 410 de 460;
* **a disciplina do JS** — observer registrado tarde ou retrato montado fora da
  janela devolve zero. Zero é o valor de uma página rápida, então a regressão se
  apresenta como elogio ao alvo. É a mesma classe que `tests/test_vitals_js.py`
  fixa para o `VITALS_JS` irmão, e por isso a guarda tem a mesma forma:
  verificação por POSIÇÃO no fonte, sem navegador.

A validação (execução real com Chromium) fica no check e está registrada no PR.
"""
from __future__ import annotations

import re

import pytest

from webqa.vitals_interacao import (
    JANELA_PADRAO_MS,
    LIMIAR_DE_EVENTO_MS,
    LIMITE_DE_TAREFA_MS,
    ORIGEM_OFICIAL,
    VITALS_INTERACAO_JS,
    Medidas,
    Tarefa,
    avaliar_orcamento,
    medidas_de,
    motivo_de_inp_ausente,
    resumo_de_tarefas,
    veredito_e_duro,
)

pytestmark = pytest.mark.verification


def _medidas(*duracoes, inp=None, **extra) -> Medidas:
    return Medidas(tarefas=tuple(Tarefa(duracao_ms=d) for d in duracoes), inp_ms=inp, **extra)


# ---------- Aritmética do TBT ----------

def test_tarefa_de_110ms_contribui_60ms():
    """Os primeiros 50ms não entram: toda tarefa precisa de algum tempo para
    existir, e cobrar por eles transformaria trabalho normal em dívida."""
    assert Tarefa(duracao_ms=110).bloqueio_ms == 60
    assert _medidas(110).tbt_ms == 60


def test_borda_exata_de_50ms_contribui_zero_e_nao_e_long_task():
    """A borda importa porque é onde a casa e o navegador precisam concordar.

    A Long Tasks API não reporta tarefa de exatamente 50ms — o corte é
    ESTRITAMENTE maior. Contar uma tarefa fabricada de 50ms como longa faria o
    teste discordar do navegador na única fronteira que ele mede, e o desacordo
    apareceria como um long task a mais que ninguém consegue localizar na aba de
    performance.
    """
    borda = Tarefa(duracao_ms=LIMITE_DE_TAREFA_MS)
    assert borda.bloqueio_ms == 0
    assert not borda.longa
    assert _medidas(50).tbt_ms == 0
    assert _medidas(50).long_tasks_n == 0
    # E logo acima da borda já conta, senão o teste acima provaria só que a
    # função devolve zero para tudo.
    assert Tarefa(duracao_ms=50.5).longa


def test_seis_blocos_sincronos_sao_UMA_task_de_660ms_nao_seis():
    """A lição da OS-40, que custou um diagnóstico no navegador real.

    O alvo fixture ganhou seis bloqueios síncronos de 110ms e o navegador
    reportou **uma** long task de 660ms: seis blocos no mesmo retorno ao laço de
    eventos são uma tarefa só. A API mede o que o laço vê, não o que o código
    escreveu. Foi preciso reagendar cada bloco por `setTimeout` para produzir
    seis tarefas — e a sonda da OS-46 confirmou `[110, 110, 109, 110, 109, 109]`.

    A consequência é o motivo de existirem DOIS orçamentos: mesmo bloqueio total,
    contagens diferentes. Um orçamento só de TBT aprovaria por pouco a página que
    trava uma vez por 660ms; um orçamento só de contagem aprovaria a que trava
    seis vezes. Este teste guarda a diferença de quem for "simplificar" um deles.
    """
    uma_so = _medidas(660)
    assert uma_so.long_tasks_n == 1
    assert uma_so.tbt_ms == 610

    seis = _medidas(110, 110, 110, 110, 110, 110)
    assert seis.long_tasks_n == 6
    assert seis.tbt_ms == 360

    assert uma_so.tbt_ms != seis.tbt_ms, "o mesmo bloqueio bruto não dá o mesmo TBT"


def test_tarefa_curta_nao_entra_no_tbt_nem_na_contagem():
    assert _medidas(10, 20, 30).tbt_ms == 0
    assert _medidas(10, 20, 30).long_tasks_n == 0


def test_pagina_sem_tarefa_longa_tem_tbt_zero_e_isso_e_medida():
    """Zero AQUI é medida legítima (nenhuma tarefa longa), diferente do zero que
    vem de não ter observado nada — o coletor é quem distingue os dois, e a
    guarda de disciplina abaixo é o que garante a distinção."""
    assert _medidas().tbt_ms == 0
    assert _medidas().long_tasks_n == 0


# ---------- Tradução do bruto ----------

def test_bruto_do_navegador_vira_medidas():
    medidas = medidas_de({
        "tarefas": [{"inicio_ms": 120.5, "duracao_ms": 110.2},
                    {"inicio_ms": 300.0, "duracao_ms": 60.0}],
        "inp_ms": 112.0, "suporta_longtask": True, "suporta_event": True,
    })
    assert medidas.long_tasks_n == 2
    assert medidas.tbt_ms == pytest.approx(70.2)
    assert medidas.inp_ms == 112.0
    assert medidas.suporta_longtask and medidas.suporta_event


def test_inp_ausente_permanece_none_e_nunca_vira_zero():
    """Zero significaria "respondeu instantaneamente" — o oposto de "não medi"."""
    assert medidas_de({"tarefas": [], "inp_ms": None}).inp_ms is None
    assert medidas_de({}).inp_ms is None
    assert medidas_de(None).inp_ms is None


def test_coletor_ilegivel_nao_derruba_a_observacao():
    """Instrumentação não pode ser a causa de uma execução perdida."""
    assert medidas_de({"tarefas": [{}]}).tarefas[0].duracao_ms == 0


# ---------- Orçamento ----------

_ORCAMENTO = {"tbt_max": 200, "inp_max": 200, "long_tasks_max": 5}


def test_dentro_do_orcamento_nao_produz_problema():
    assert avaliar_orcamento(_medidas(60, 60, inp=40), **_ORCAMENTO) == []


def test_tbt_estourado_nomeia_o_numero_e_o_orcamento():
    problemas = avaliar_orcamento(_medidas(*[110] * 6, inp=40), **_ORCAMENTO)
    assert any("TBT 360ms" in p and "200ms" in p for p in problemas)


def test_contagem_e_tbt_sao_problemas_SEPARADOS():
    """Seis tarefas de 110ms estouram os dois; uma de 660ms estoura só o TBT.

    Se os dois virassem um problema só, o laudo não diria qual corrigir — e a
    correção é outra em cada caso (dividir o trabalho × reduzi-lo)."""
    seis = avaliar_orcamento(_medidas(*[110] * 6), **_ORCAMENTO)
    uma = avaliar_orcamento(_medidas(660), **_ORCAMENTO)
    assert len(seis) == 2
    assert len(uma) == 1 and "TBT" in uma[0]


def test_inp_ausente_nao_e_tratado_como_estouro():
    """Ausência de medida não é veredito — quem chama decide o que fazer com ela."""
    assert avaliar_orcamento(_medidas(), **_ORCAMENTO) == []


def test_inp_acima_do_orcamento_entra_como_problema_proprio():
    problemas = avaliar_orcamento(_medidas(inp=420), **_ORCAMENTO)
    assert len(problemas) == 1 and "INP aproximado 420ms" in problemas[0]


def test_motivo_do_inp_ausente_distingue_nao_suportado_de_nao_observado():
    """Skip que não diz qual dos dois é obriga o leitor a reproduzir o run."""
    sem_api = motivo_de_inp_ausente(_medidas(suporta_event=False))
    sem_evento = motivo_de_inp_ausente(_medidas(suporta_event=True))
    assert "indisponível nesta engine" in sem_api
    assert "Nenhum evento de interação" in sem_evento
    assert "não é rapidez" in sem_evento


def test_resumo_lista_as_tarefas_mais_caras_primeiro():
    texto = resumo_de_tarefas([Tarefa(duracao_ms=80), Tarefa(duracao_ms=300, inicio_ms=90)])
    assert texto.splitlines()[0].strip().startswith("tarefa de 300ms")
    assert "t=90ms" in texto


def test_resumo_trunca_dizendo_quantos_ficaram():
    assert "e mais 5" in resumo_de_tarefas([Tarefa(duracao_ms=100)] * 15, teto=10)


# ---------- Origem: o veredito é do ambiente oficial ----------

def test_so_a_origem_oficial_endurece_o_veredito():
    assert veredito_e_duro("vps")
    assert veredito_e_duro(" VPS ")          # o compose pode passar com espaço
    assert not veredito_e_duro("ci")
    assert not veredito_e_duro("local")
    assert not veredito_e_duro(None)
    assert not veredito_e_duro("")


def test_origem_oficial_nao_divergiu_do_ledger():
    """A constante existe em dois lugares porque `webqa/` não depende de
    `scripts/`. Duas cópias divergem no primeiro dia em que alguém mexe numa
    delas — e a divergência apareceria como um check reprovando na VPS enquanto o
    ledger contabiliza a execução como "local"."""
    from scripts.estabilidade import ORIGEM_OFICIAL as DO_LEDGER
    assert ORIGEM_OFICIAL == DO_LEDGER


# ---------- Disciplina do coletor (mesma forma de tests/test_vitals_js.py) ----------

# Montagem do retrato: precisa acontecer DEPOIS da janela de observação.
LEITURAS = ("inp_ms:", "tarefas.slice()")
# Registro de observador: precisa acontecer ANTES, para escutar durante a janela.
OBSERVADORES = ("PerformanceObserver",)


def _limites_da_callback() -> tuple[int, int]:
    """(início, fim) do corpo da callback do setTimeout, por posição no fonte."""
    inicio = VITALS_INTERACAO_JS.find("setTimeout(")
    assert inicio > 0, "o coletor precisa resolver dentro de um setTimeout"
    fim = VITALS_INTERACAO_JS.find("}, janela_ms)", inicio)
    assert fim > inicio, "a callback do setTimeout precisa fechar com a janela"
    return inicio, fim


def test_o_retrato_e_montado_dentro_da_callback():
    """A regressão exata do irmão: retrato montado em t=0 e resolvido 2s depois.

    Montado fora, `tarefas.slice()` congelaria um array vazio e `inp` congelaria
    `null` — e a janela de 2s não serviria de nada. O laudo diria "TBT 0ms" numa
    página que travou 600ms, que é elogio ao alvo em vez de achado.
    """
    inicio, _ = _limites_da_callback()
    for leitura in LEITURAS:
        fora = [m.start() for m in re.finditer(re.escape(leitura), VITALS_INTERACAO_JS)
                if m.start() < inicio]
        assert not fora, (
            f"'{leitura}' aparece ANTES do setTimeout (posição {fora}) — a janela de "
            "observação não serve de nada se o retrato é montado antes dela.")


def test_observadores_ficam_registrados_antes_da_janela():
    """`longtask` e `event` são FLUXOS, não estado consultável: observer
    registrado dentro da callback perderia tudo o que aconteceu na carga — que é
    justamente o período em que uma página pesada trava."""
    inicio, _ = _limites_da_callback()
    antes = VITALS_INTERACAO_JS[:inicio]
    for observador in OBSERVADORES:
        assert observador in antes, f"{observador} precisa ser registrado antes do setTimeout"


def test_todo_observer_pede_buffered():
    """Sem `buffered: true`, o observer só vê o que acontecer DEPOIS do registro.

    Como o coletor entra por `add_init_script`, o buraco seria pequeno — e é
    exatamente por isso que a regressão passaria despercebida: some a primeira
    long task, o TBT cai um pouco, e o número segue plausível.
    """
    registros = re.findall(r"\.observe\(\{[^}]*\}\)", VITALS_INTERACAO_JS)
    assert len(registros) == 3, "longtask, event e first-input — três observers"
    for registro in registros:
        assert "buffered: true" in registro, f"observer sem buffered: {registro}"


def test_inp_comeca_em_null_e_as_tarefas_em_lista_vazia():
    """Ausência tem de ser distinguível de zero: página que não registrou
    interação nenhuma não é uma página que responde instantaneamente."""
    assert re.search(r"inp:\s*null", VITALS_INTERACAO_JS)
    assert re.search(r"tarefas:\s*\[\]", VITALS_INTERACAO_JS)


def test_suporte_e_detectado_em_runtime_nao_pela_engine():
    """`longtask` e `event` são Chromium-only hoje, mas "hoje" muda. Perguntar ao
    navegador o que ele suporta envelhece melhor que uma lista de engines no
    código da suíte — e não mente quando a lista fica velha."""
    assert "supportedEntryTypes" in VITALS_INTERACAO_JS
    assert "'longtask'" in VITALS_INTERACAO_JS
    assert "'event'" in VITALS_INTERACAO_JS


def test_event_timing_usa_o_limiar_baixo_e_declarado():
    """O padrão da API é 104ms: com ele, uma interação de 60ms — ruim, mas não
    catastrófica — não seria reportada, e o INP sairia nulo numa página lenta."""
    assert f"durationThreshold: {LIMIAR_DE_EVENTO_MS}" in VITALS_INTERACAO_JS
    assert LIMIAR_DE_EVENTO_MS == 16, "16ms é o mínimo que a Event Timing API aceita"


def test_first_input_e_a_rede_de_seguranca_da_interacao_rapida():
    """`first-input` NÃO obedece a `durationThreshold`. Sem ele, o Tab numa página
    saudável (16ms, medido na sonda) ficaria abaixo do limiar, o INP sairia nulo
    e o check pularia SEMPRE — "não medido" indistinguível de "não suportado"."""
    assert "'first-input'" in VITALS_INTERACAO_JS


def test_a_janela_e_parametro_e_tem_padrao_declarado():
    """Janela fixa no JS obrigaria a editar o coletor para medir mais tempo."""
    assert "janela_ms" in VITALS_INTERACAO_JS
    assert JANELA_PADRAO_MS == 2000
