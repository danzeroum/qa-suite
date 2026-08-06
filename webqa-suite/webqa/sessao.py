"""Sessão moderada com pessoas: o que dela vira número (OS-54).

A camada `gui` mede o que o navegador mostra. Satisfação, confiança, carga
cognitiva e clareza de rótulo continuam exigindo gente — é a ressalva que a nota
epistêmica do `docs/GUI.md` faz desde a primeira linha, e este módulo é o que a
torna acionável em vez de decorativa.

**Mesmos nomes, mesmas unidades, ORIGEM distinta.** `gui_jornada_tsr` humano e
sintético são a mesma régua medida de dois jeitos — é o que a OS-51 comprou ao
escrever os cenários para pessoa e robô ao mesmo tempo. Comparáveis, e por isso
mesmo **jamais confundíveis**: toda medida carrega `fonte=humano|sintetico`, e
misturar as duas numa média seria inventar um terceiro número que não descreve
nem uma coisa nem outra.

**A lei da casa vale para dentro.** Resposta ausente não vira zero: quem não
respondeu ao SEQ não achou a tarefa fácil nem difícil, e gravar 0 puxaria a
mediana para baixo transformando falta de dado em veredito sobre o alvo. É o
mesmo `webqa/metricas.py::registrar` recusando `None`, aplicado a gente.

**Minimização é de desenho, não de disciplina.** Nada aqui aceita nome: o
participante é iniciais + perfil, e a transcrição passa por `sanitize_text` antes
de tocar o disco (`scripts/consolida_sessao.py`).

Somente stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# SUS: 10 itens, escala 1–5. Ímpares são afirmações POSITIVAS (pontuam
# resposta−1), pares são NEGATIVAS (pontuam 5−resposta). A soma vai de 0 a 40 e
# é multiplicada por 2,5 para virar 0–100. Não é percentual, e chamar de
# "porcentagem de satisfação" é o erro clássico: 68 é a média da literatura, não
# "68% de aprovação".
SUS_ITENS = 10
SUS_MIN, SUS_MAX = 1, 5
SUS_FATOR = 2.5

# SEQ: item único, 1–7, aplicado LOGO APÓS cada tarefa. Sete e não cinco porque é
# assim que a escala é publicada, e mudar a granularidade quebraria a comparação
# com qualquer referência externa.
SEQ_MIN, SEQ_MAX = 1, 7

# Severidade de Nielsen, 0–4. Vocabulário dele, verbatim: renomear os graus
# tornaria o achado incomparável com qualquer relatório de usabilidade.
SEVERIDADE_NIELSEN = {
    0: "não é problema de usabilidade",
    1: "cosmético — corrigir se sobrar tempo",
    2: "menor — prioridade baixa",
    3: "maior — prioridade alta",
    4: "catástrofe — corrigir antes de publicar",
}

FONTE_HUMANO = "humano"
FONTE_SINTETICO = "sintetico"


def _no_intervalo(valor, minimo: int, maximo: int) -> bool:
    return isinstance(valor, (int, float)) and minimo <= valor <= maximo


def sus(respostas) -> float | None:
    """Pontuação SUS 0–100. `None` quando o questionário não foi respondido.

    Exige os DEZ itens: a escala é validada como conjunto, e pontuar sete itens
    produziria um número na mesma faixa que não é comparável com nada. Devolver
    `None` é dizer "não medi" — devolver 70 seria dizer "medi e deu 70".
    """
    if respostas is None or len(respostas) != SUS_ITENS:
        return None
    if not all(_no_intervalo(r, SUS_MIN, SUS_MAX) for r in respostas):
        return None
    bruto = 0.0
    for indice, resposta in enumerate(respostas):
        positivo = indice % 2 == 0          # itens 1, 3, 5, 7, 9 (base zero: pares)
        bruto += (resposta - SUS_MIN) if positivo else (SUS_MAX - resposta)
    return round(bruto * SUS_FATOR, 1)


def seq(resposta) -> float | None:
    """SEQ 1–7 de UMA tarefa. `None` quando não respondida.

    Ausência NÃO vira zero — e zero nem existe nesta escala, o que torna o erro
    ainda mais visível: um 0 gravado aqui seria um valor fora do domínio sendo
    lido como "muito difícil".
    """
    return float(resposta) if _no_intervalo(resposta, SEQ_MIN, SEQ_MAX) else None


@dataclass(frozen=True)
class Tarefa:
    """O que uma pessoa fez numa tarefa do roteiro."""

    cenario: str
    concluiu: bool = False
    segundos: float | None = None
    cliques: int | None = None
    seq: float | None = None

    @property
    def tsr(self) -> int:
        return 1 if self.concluiu else 0


# Pesos do SUM (Single Usability Metric). DECLARADOS, e a declaração importa
# mais que os valores: qualquer combinação de conclusão, tempo e satisfação num
# número só é uma escolha, não um fato. Iguais por decisão — sem evidência local
# que justifique privilegiar um eixo, pesos iguais é a única escolha que não
# esconde uma opinião dentro de uma média.
PESOS_SUM = {"conclusao": 1 / 3, "satisfacao": 1 / 3, "tempo": 1 / 3}


def sum_de(tarefas, tempo_alvo_s: float) -> float | None:
    """SUM 0–100 de um conjunto de tarefas. `None` sem tarefa avaliável.

    Combina três eixos normalizados. O de TEMPO é razão contra um alvo declarado
    e é limitado a 1: concluir mais rápido que o alvo não compra crédito para
    compensar uma tarefa que ninguém terminou.
    """
    avaliaveis = [t for t in (tarefas or []) if t.segundos is not None or t.seq is not None]
    if not avaliaveis or tempo_alvo_s <= 0:
        return None
    conclusao = sum(t.tsr for t in avaliaveis) / len(avaliaveis)
    notas = [t.seq for t in avaliaveis if t.seq is not None]
    satisfacao = ((sum(notas) / len(notas)) - SEQ_MIN) / (SEQ_MAX - SEQ_MIN) if notas else 0.0
    tempos = [t.segundos for t in avaliaveis if t.segundos is not None]
    tempo = min(1.0, tempo_alvo_s / (sum(tempos) / len(tempos))) if tempos else 0.0
    total = (PESOS_SUM["conclusao"] * conclusao
             + PESOS_SUM["satisfacao"] * satisfacao
             + PESOS_SUM["tempo"] * tempo)
    return round(total * 100, 1)


@dataclass(frozen=True)
class Achado:
    """Um problema observado na sessão, com severidade de Nielsen."""

    descricao: str
    severidade: int
    cenario: str = ""
    criterio: str = ""

    def __post_init__(self):
        if self.severidade not in SEVERIDADE_NIELSEN:
            raise ValueError(
                f"severidade inválida: {self.severidade!r}. Use 0–4 "
                f"(Nielsen): {SEVERIDADE_NIELSEN}")

    @property
    def rotulo(self) -> str:
        return SEVERIDADE_NIELSEN[self.severidade]


@dataclass(frozen=True)
class Sessao:
    """Uma sessão moderada. Participante por INICIAIS e perfil — nunca nome."""

    iniciais: str
    perfil: str
    tarefas: tuple[Tarefa, ...] = ()
    respostas_sus: tuple[float, ...] | None = None
    achados: tuple[Achado, ...] = ()
    notas: str = ""
    consentimento: dict = field(default_factory=dict)


def metricas_de(sessao: Sessao, tempo_alvo_s: float) -> dict:
    """As medidas da sessão, com os MESMOS nomes das sintéticas e `fonte=humano`.

    Chave por cenário para alinhar com `gui_jornada_*` do laudo automatizado —
    é isso que permite `webqa/comparador.py` pôr as duas ao lado sem que ninguém
    precise traduzir nome de métrica no meio da leitura.
    """
    fora: dict[str, dict] = {}
    for tarefa in sessao.tarefas:
        chave = tarefa.cenario.replace(" ", "_")
        fora[f"gui_jornada_tsr_{chave}"] = {"valor": tarefa.tsr, "fonte": FONTE_HUMANO}
        if tarefa.segundos is not None:
            fora[f"gui_jornada_tot_ms_{chave}"] = {"valor": round(tarefa.segundos * 1000, 1),
                                                  "fonte": FONTE_HUMANO}
        if tarefa.cliques is not None:
            fora[f"gui_jornada_cliques_{chave}"] = {"valor": tarefa.cliques,
                                                   "fonte": FONTE_HUMANO}
        if tarefa.seq is not None:
            fora[f"gui_sessao_seq_{chave}"] = {"valor": tarefa.seq, "fonte": FONTE_HUMANO}
    pontuacao = sus(sessao.respostas_sus)
    if pontuacao is not None:
        fora["gui_sessao_sus"] = {"valor": pontuacao, "fonte": FONTE_HUMANO}
    total = sum_de(sessao.tarefas, tempo_alvo_s)
    if total is not None:
        fora["gui_sessao_sum"] = {"valor": total, "fonte": FONTE_HUMANO}
    return fora


def problemas_do_consentimento(consentimento) -> list[str]:
    """O consentimento declara o que a LGPD exige declarar?

    A casa cobra isso de todo alvo que audita; cobrá-lo de si mesma não é
    simetria decorativa — é a única forma de a bateria de LGPD não ser uma
    exigência que o próprio projeto não cumpre.
    """
    obrigatorios = ("finalidade", "retencao_dias", "expurgo", "gravacao", "data")
    faltando = [c for c in obrigatorios if not str((consentimento or {}).get(c) or "").strip()]
    problemas = []
    if faltando:
        problemas.append(
            f"consentimento sem {faltando} — sessão sem finalidade, prazo e forma de "
            f"expurgo declarados é coleta que ninguém consegue auditar depois.")
    prazo = (consentimento or {}).get("retencao_dias")
    if prazo is not None and not (isinstance(prazo, int) and 0 < prazo <= 365):
        problemas.append(
            f"retencao_dias={prazo!r} fora de 1–365. Retenção indefinida é o oposto de "
            f"prazo declarado, e o expurgo precisa de uma data para acontecer.")
    return problemas
