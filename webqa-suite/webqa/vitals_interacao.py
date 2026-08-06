"""Interatividade medida: TBT, long tasks e INP aproximado.

Fecha a lacuna mais cara do `VITALS_JS` de `checks/frontend/test_rendering.py`,
que observa pintura (LCP) e estabilidade (CLS) e **não observa bloqueio**. Uma
página pode pintar em 400ms e ficar surda ao teclado por mais um segundo: as
Web Vitals de carga aprovam, e quem usa a página sente o contrário.

Três medidas, e a diferença entre elas importa:

* **long tasks** — quantas vezes a thread principal ficou presa acima de 50ms;
* **TBT** — quanto tempo, somado, ela ficou presa ALÉM desses 50ms. É o proxy de
  laboratório do INP: mede a *disponibilidade* para responder, não uma resposta;
* **INP aproximado** — a maior latência de evento observada. É a única das três
  que mede uma interação de verdade.

**A lição que este módulo existe para não deixar morrer no histórico do PR.**
Na OS-40 o alvo fixture ganhou seis bloqueios síncronos de 110ms, e o navegador
reportou **uma** long task de 660ms, não seis de 110ms. Motivo: seis blocos
síncronos no mesmo retorno ao laço de eventos são uma única tarefa — a API mede
o que o laço vê, não o que o código escreveu. Foi preciso reagendar cada bloco
por `setTimeout` para produzir seis tarefas. A consequência vale para qualquer
alvo: **contagem de long tasks e TBT não são redutíveis um ao outro**, e um
orçamento só de TBT aprovaria uma página que trava uma vez por 660ms.
`tests/test_vitals_interacao.py` fixa os dois casos lado a lado.

**Limite declarado do INP.** O INP de campo é o percentil ~98 das interações de
uma sessão real. Aqui há UMA interação, neutra e sintética (`Tab`), então o que
se mede é a maior latência observada numa janela curta — um **limite inferior**
do INP real, útil para pegar o caso grosseiro e incapaz de descrever a cauda.
Chamar isso de INP sem a ressalva prometeria uma medida de campo a partir de
uma amostra de laboratório.

Somente stdlib. O núcleo é puro: recebe o que o navegador devolveu, decide, e
não sabe o que é uma página.
"""
from __future__ import annotations

from dataclasses import dataclass

# Definição da Long Tasks API e ponto de corte do TBT no Lighthouse — não é um
# limiar da casa. Mudá-lo aqui faria a medida deixar de ser comparável com
# qualquer outra ferramenta que reporte TBT, e o número perderia o sentido que
# justifica medi-lo.
LIMITE_DE_TAREFA_MS = 50.0

# Janela de observação DEPOIS da interação neutra. Evento de teclado pode ser
# processado em vários quadros (keydown, input, render); resolver no instante do
# Tab leria a latência antes de ela existir.
JANELA_PADRAO_MS = 2000

# Menor valor que a Event Timing API aceita em `durationThreshold`. O padrão da
# API é 104ms: com ele, uma interação de 60ms — ruim, mas não catastrófica —
# simplesmente não seria reportada, e o INP sairia `null` numa página lenta.
LIMIAR_DE_EVENTO_MS = 16

# Ambiente em que o estouro de orçamento vira veredito. Mesmo valor que
# `scripts/estabilidade.py::ORIGEM_OFICIAL`, e `tests/test_vitals_interacao.py`
# prova que os dois não divergiram — a constante não é importada de lá porque
# `webqa/` não depende de `scripts/`, e inverter a camada por uma string de três
# letras sairia mais caro que o teste que amarra as duas.
ORIGEM_OFICIAL = "vps"


def veredito_e_duro(origem_declarada: str | None) -> bool:
    """O estouro reprova, ou vira aviso?

    TBT oscila por fatores fora do alvo: runner compartilhado, vizinho barulhento,
    CPU com governor variável. Num CI assim, um limiar afrouxado até caber seria o
    R5 se realizando — o número deixa de significar qualquer coisa e o teste vira
    decoração. A saída da casa é outra: **a régua não muda, o peso do veredito
    muda**. No ambiente oficial (`docs/VPS.md`) o estouro reprova; fora dele vira
    `xfail` com o motivo escrito, e a MEDIDA é registrada dos dois jeitos.

    Recebe o valor em vez de ler o ambiente para que o teste não precise de
    monkeypatch para exercitar os dois lados — a mesma razão de `caminhar` receber
    as ações em `webqa/foco.py`.
    """
    return (origem_declarada or "").strip().lower() == ORIGEM_OFICIAL


@dataclass(frozen=True)
class Tarefa:
    """Uma tarefa longa como a Long Tasks API a reporta."""

    duracao_ms: float
    inicio_ms: float = 0.0

    @property
    def longa(self) -> bool:
        """Estritamente MAIOR que 50ms.

        A borda importa: a API não reporta tarefa de exatamente 50ms, e contar
        uma tarefa fabricada de 50ms como longa faria o teste da casa discordar
        do navegador na única fronteira em que os dois precisam concordar.
        """
        return self.duracao_ms > LIMITE_DE_TAREFA_MS

    @property
    def bloqueio_ms(self) -> float:
        """O que esta tarefa contribui ao TBT: o excedente sobre os 50ms.

        Os primeiros 50ms não entram porque toda tarefa precisa de algum tempo
        para existir; cobrar por eles transformaria trabalho normal em dívida.
        """
        return max(0.0, self.duracao_ms - LIMITE_DE_TAREFA_MS)

    def __str__(self) -> str:
        return (f"tarefa de {self.duracao_ms:.0f}ms em t={self.inicio_ms:.0f}ms "
                f"(bloqueia {self.bloqueio_ms:.0f}ms)")


@dataclass(frozen=True)
class Medidas:
    """O que a janela de observação produziu — medida, nunca veredito."""

    tarefas: tuple[Tarefa, ...] = ()
    inp_ms: float | None = None
    suporta_longtask: bool = False
    suporta_event: bool = False

    @property
    def longas(self) -> tuple[Tarefa, ...]:
        return tuple(t for t in self.tarefas if t.longa)

    @property
    def long_tasks_n(self) -> int:
        return len(self.longas)

    @property
    def tbt_ms(self) -> float:
        return round(sum(t.bloqueio_ms for t in self.tarefas), 3)


def medidas_de(bruto) -> Medidas:
    """Traduz o dicionário devolvido pelo coletor. Tolerante por decisão:
    instrumentação ilegível não pode derrubar a observação do alvo."""
    bruto = bruto or {}
    tarefas = tuple(
        Tarefa(duracao_ms=float(t.get("duracao_ms") or 0.0),
               inicio_ms=float(t.get("inicio_ms") or 0.0))
        for t in (bruto.get("tarefas") or [])
    )
    inp = bruto.get("inp_ms")
    return Medidas(
        tarefas=tarefas,
        inp_ms=None if inp is None else float(inp),
        suporta_longtask=bool(bruto.get("suporta_longtask")),
        suporta_event=bool(bruto.get("suporta_event")),
    )


def avaliar_orcamento(medidas: Medidas, *, tbt_max: float, inp_max: float,
                      long_tasks_max: float) -> list[str]:
    """Os estouros, um por linha — puro, e é o que permite testá-lo sem navegador.

    Devolve LISTA e não booleano porque o laudo precisa dizer qual dos três
    orçamentos estourou: "interatividade ruim" não diz se a página trava uma vez
    por muito tempo ou muitas vezes por pouco, e a correção é outra em cada caso.

    INP ausente NÃO vira problema aqui — ausência de medida não é veredito, e
    quem chama decide o que fazer com ela (`motivo_de_inp_ausente`).
    """
    problemas = []
    if medidas.tbt_ms > tbt_max:
        problemas.append(
            f"TBT {medidas.tbt_ms:.0f}ms acima do orçamento de {tbt_max:.0f}ms — a thread "
            "principal ficou indisponível para responder por esse tempo somado.")
    if medidas.long_tasks_n > long_tasks_max:
        problemas.append(
            f"{medidas.long_tasks_n} long tasks acima de {LIMITE_DE_TAREFA_MS:.0f}ms "
            f"(limite {long_tasks_max:.0f}) — cada uma é uma janela em que o clique e a "
            "tecla ficam sem resposta.")
    if medidas.inp_ms is not None and medidas.inp_ms > inp_max:
        problemas.append(
            f"INP aproximado {medidas.inp_ms:.0f}ms acima de {inp_max:.0f}ms — a interação "
            "medida demorou a produzir efeito visível.")
    return problemas


def motivo_de_inp_ausente(medidas: Medidas) -> str:
    """Por que não houve INP — distingue 'não suportado' de 'nada foi observado'."""
    if not medidas.suporta_event:
        return ("Event Timing API indisponível nesta engine: INP não medido. "
                "TBT e long tasks seguem valendo.")
    return ("Nenhum evento de interação chegou à janela de observação — INP não medido. "
            "Ausência de medida não é rapidez.")


def resumo_de_tarefas(tarefas, teto: int = 10) -> str:
    """As mais caras primeiro: quem for corrigir começa pela maior."""
    ordenadas = sorted(tarefas, key=lambda t: t.duracao_ms, reverse=True)
    linhas = [f"  {t}" for t in ordenadas[:teto]]
    if len(ordenadas) > teto:
        linhas.append(f"  … e mais {len(ordenadas) - teto}")
    return "\n".join(linhas)


# ---------- Coletor ----------

# Instalado por `add_init_script` ANTES do `goto`, e a ordem não é preferência:
# `longtask` e `event` são fluxos de eventos, não estado consultável. Observer
# registrado depois da carga perde tudo o que aconteceu durante ela — que é
# justamente o período em que uma página pesada trava.
#
# A disciplina é a mesma que `tests/test_vitals_js.py` fixa para o `VITALS_JS`
# irmão, e por isso `tests/test_vitals_interacao.py` a refixa aqui:
#
# * observers registrados FORA da callback da janela, com `buffered: true` —
#   eles precisam estar escutando DURANTE a observação;
# * o retrato (`inp_ms:`, `tarefas.slice()`) montado DENTRO da callback. Montado
#   fora, `slice()` congelaria um array vazio e `inp` congelaria `null` — e a
#   janela de 2s não serviria de nada, exatamente o bug que o irmão já teve;
# * `inp` começa em `null`, nunca em 0: página que não registrou interação
#   nenhuma não é uma página que responde instantaneamente.
VITALS_INTERACAO_JS = """
(() => {
  const suportados = (window.PerformanceObserver
      && PerformanceObserver.supportedEntryTypes) || [];
  const estado = {
    tarefas: [],
    inp: null,
    suporta_longtask: suportados.indexOf('longtask') >= 0,
    suporta_event: suportados.indexOf('event') >= 0,
  };
  const maiorInp = (entradas) => {
    for (const e of entradas) {
      if (estado.inp === null || e.duration > estado.inp) { estado.inp = e.duration; }
    }
  };
  if (estado.suporta_longtask) {
    try {
      new PerformanceObserver(l => {
        for (const e of l.getEntries()) {
          estado.tarefas.push({inicio_ms: e.startTime, duracao_ms: e.duration});
        }
      }).observe({type: 'longtask', buffered: true});
    } catch (err) { estado.suporta_longtask = false; }
  }
  if (estado.suporta_event) {
    try {
      new PerformanceObserver(l => maiorInp(l.getEntries()))
          .observe({type: 'event', buffered: true, durationThreshold: __LIMIAR__});
    } catch (err) { estado.suporta_event = false; }
  }
  // `first-input` NÃO obedece a durationThreshold: é a rede de segurança para a
  // interação rápida, que o observer acima descarta por ser curta demais. Sem
  // ela, uma página saudável devolveria INP nulo e o check pularia sempre —
  // "não medido" indistinguível de "não suportado".
  try {
    new PerformanceObserver(l => maiorInp(l.getEntries()))
        .observe({type: 'first-input', buffered: true});
  } catch (err) { /* engine sem first-input: o observer de evento basta */ }
  window.__webqa_interacao = (janela_ms) => new Promise(resolve => {
    setTimeout(() => {
      resolve({
        tarefas: estado.tarefas.slice(),
        inp_ms: estado.inp,
        suporta_longtask: estado.suporta_longtask,
        suporta_event: estado.suporta_event,
      });
    }, janela_ms);
  });
})();
""".replace("__LIMIAR__", str(LIMIAR_DE_EVENTO_MS))
