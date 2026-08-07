"""Veredito do PROCESSO: os três estados sobem do laudo ao código de saída.

**O defeito, com mecanismo.** `conftest.py::alvo_alcancavel` é preflight de sessão:
com o alvo fora do ar ele derruba TUDO em skip, e o pytest, com tudo pulado, sai
**0**. `docker/entrypoint.sh` encadeia com `|| true` de propósito. O resultado é
que *"não consegui medir"* sai com a mesma cor de *"medi e está bom"* — e a cor
mais barata vence por hábito. Um verde que significa "não olhei" encerra a
investigação com a convicção de quem olhou.

**A semântica já existia; faltava a altura.** `vitals_interacao.veredito_e_duro`
("a régua não muda, o peso do veredito muda"), `auth` ("erro de infraestrutura não
é veredito sobre o alvo") e `report` (`error` ≠ `failed` ≠ `skipped`) já
distinguem os três estados NO NÍVEL DOS CHECKS. O que faltava era isso chegar ao
exit do processo, que é onde uma guarda de CI lê veredito.

**O mapa não foi inventado aqui — foi PROMOVIDO.** O consumidor já o escrevia, em
`ci/suite_runner.py::traduzir_veredito`, INFERINDO o veredito de um laudo que não
o declarava. Inferência não é laudo: quem mede é quem sabe. Trazer o mapa para a
origem é o que torna aquele remendo apagável em vez de mascarado.

**Os códigos, e por que não colidem com os do pytest.** O pytest usa 0–5
(0 ok, 1 falhas, 2 interrompido, 3 erro interno, 4 uso, 5 nenhum teste). Os deste
comando começam em 10 POR ESCOLHA: as duas saídas convivem no mesmo pipeline —
`pytest` roda, este comando lê o laudo — e um código repetido faria quem lê o log
atribuir ao pytest um veredito que é deste comando, ou o contrário.

    0   nenhuma violação observada  (R10: passar NÃO certifica)
    10  violação observada          (a régua mediu e reprovou)
    20  INDETERMINADO — bloqueia    (não mediu: alvo fora do ar, tudo pulado,
                                     erro de infraestrutura, laudo vazio)
    30  configuração inválida       (laudo ausente, ilegível ou sem forma)

**O que este comando NÃO faz.** Não roda teste, não toca no alvo, não altera o
exit do pytest, do `make verify`, dos `afere_*`, do ledger nem o `|| true` do
entrypoint. Ele LÊ o laudo que já existe e traduz. Um veredito que também
executasse teria dois motivos para falhar, e quem lê o exit não saberia qual.

**Veredito se lê do EXIT CODE, nunca da primeira linha da saída.** A saída em
texto é para pessoas; a decisão é o código.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SEM_VIOLACAO = 0
VIOLACAO = 10
INDETERMINADO = 20
CONFIG_INVALIDA = 30

# Estados do laudo (webqa/report.py::pytest_runtest_logreport) e o que cada um
# significa para o veredito do processo. A tabela é explícita porque a decisão
# mais cara desta casa mora aqui: `xfail` e `skipped` NUNCA viram achado.
#
#   failed   → o check mediu o alvo e reprovou. É violação.
#   error    → o teste não aconteceu (estourou fora do corpo). Erro de
#              infraestrutura não é veredito sobre o alvo.
#   skipped  → não avaliado. Não é "conforme"; também não é achado.
#   xfail    → desfecho esperado por AMBIENTE (origem declarada, engine, tempo).
#              Exportá-lo como achado transformaria "não afirmei" em "defeito
#              medido", que é a mentira mais cara que um laudo pode contar.
#   passed   → nenhuma violação OBSERVADA. Nunca "conforme".
ESTADOS_QUE_MEDIRAM = frozenset({"passed", "failed"})


@dataclass(frozen=True)
class Veredito:
    """O veredito e o porquê. `codigo` é o que a guarda lê."""

    codigo: int
    estado: str
    motivo: str

    @property
    def inconclusivo(self) -> bool:
        """Um só lugar decide o que é inconclusivo — o laudo e o exit não podem
        discordar, e a única forma de garantir isso é não haver duas contas."""
        return self.codigo == INDETERMINADO


def _contar(laudo: dict) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for r in laudo.get("results") or []:
        estado = r.get("estado") or r.get("outcome") or "?"
        contagem[estado] = contagem.get(estado, 0) + 1
    return contagem


def avaliar(laudo: dict) -> Veredito:
    """O veredito de um laudo já lido. Puro: é o que permite testá-lo nos três
    estados sobre laudos fabricados, inclusive os que não dá para produzir.

    A ORDEM das perguntas é a decisão. "Houve violação?" vem antes de "mediu o
    suficiente?" porque uma violação observada é observação, e não deixa de ser
    porque outra coisa não pôde ser medida: rebaixá-la a indeterminado esconderia
    um achado real atrás de um problema de ambiente.
    """
    if not isinstance(laudo, dict):
        return Veredito(CONFIG_INVALIDA, "config_invalida",
                        "o laudo não é um objeto JSON")
    if "results" not in laudo:
        return Veredito(CONFIG_INVALIDA, "config_invalida",
                        "o laudo não tem `results` — não é um summary desta suíte")

    # O PREFLIGHT vem primeiro, e é a correção mais importante desta função.
    #
    # Medido contra uma porta fechada: 58 checks viram `error` e QUATRO viram
    # `failed` — os de pytest-bdd, que fazem a requisição dentro do corpo do teste,
    # onde o ConnectError cai na fase `call`. Contar desfechos daria "4 violações":
    # quatro achados sobre um alvo que ninguém alcançou. A distinção error/failed do
    # laudo é por FASE, não por natureza, e por isso ela sozinha não decide.
    #
    # Alvo inalcançável é estado de SESSÃO. Nenhum desfecho de dentro de uma sessão
    # que não alcançou o alvo é veredito sobre o alvo.
    preflight = laudo.get("preflight")
    if isinstance(preflight, dict) and preflight.get("alcancado") is False:
        return Veredito(
            INDETERMINADO, "indeterminado",
            f"o alvo não respondeu ao primeiro GET da sessão "
            f"({preflight.get('motivo') or 'sem motivo registrado'}). Nada do que veio depois "
            f"é veredito sobre o alvo — inclusive os checks que terminaram em `failed` por "
            f"terem feito a requisição dentro do próprio corpo.")

    contagem = _contar(laudo)

    # Laudo SEM bloco de preflight — de uma versão anterior da suíte, ou de uma
    # execução em que nenhum check pediu a fixture. A pergunta é a mesma e a
    # resposta precisa ser conservadora: se NENHUM check completou e há erro, a
    # sessão não estabeleceu contato, e um `failed` ali é indistinguível do mesmo
    # problema de infraestrutura. O conjunto `error > 0` é o que separa este caso
    # do alvo que responde e reprova em tudo — lá não há erro nenhum.
    if not contagem.get("passed") and contagem.get("error"):
        return Veredito(
            INDETERMINADO, "indeterminado",
            f"nenhum check completou e {contagem['error']} não chegaram a acontecer "
            f"({dict(sorted(contagem.items()))}). Sem um único desfecho completo, um `failed` "
            f"não se distingue do mesmo problema de infraestrutura que produziu os erros.")

    if contagem.get("failed"):
        return Veredito(VIOLACAO, "violacao",
                        f"{contagem['failed']} check(s) reprovaram o alvo")

    mediram = sum(contagem.get(e, 0) for e in ESTADOS_QUE_MEDIRAM)
    if not mediram:
        return Veredito(
            INDETERMINADO, "indeterminado",
            f"nenhum check chegou a medir o alvo ({contagem or 'laudo vazio'}). "
            f"Alvo fora do ar, preflight derrubando a sessão em skip, ou seleção que "
            f"não coletou nada — em qualquer um dos casos não há veredito sobre o alvo.")
    if contagem.get("error"):
        return Veredito(
            INDETERMINADO, "indeterminado",
            f"{contagem['error']} check(s) não chegaram a acontecer (erro fora do corpo do "
            f"teste). Erro de infraestrutura não é veredito sobre o alvo, e tratá-lo como "
            f"'sem violação' é o verde por não olhar.")
    return Veredito(
        SEM_VIOLACAO, "sem_violacao_observada",
        f"{contagem.get('passed', 0)} check(s) mediram e nenhuma violação foi observada. "
        f"Isto NÃO certifica conformidade (R10): passar significa que nada foi observado, "
        f"não que nada existe.")


def ler(caminho: Path) -> tuple[dict | None, str]:
    """(laudo, motivo do erro). Laudo ausente ou ilegível é CONFIGURAÇÃO, não
    ausência de violação — o modo de falha que sairia 0 se ninguém o nomeasse."""
    if not caminho.exists():
        return None, (f"laudo ausente em {caminho}. Rodar a suíte é o que o produz; sem ele "
                      f"não há o que traduzir, e traduzir nada como 'sem violação' seria "
                      f"inventar um veredito.")
    try:
        return json.loads(caminho.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError) as erro:
        return None, f"laudo ilegível em {caminho}: {erro}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Traduz o laudo da suíte em veredito por código de saída.",
        epilog="Códigos: 0 nenhuma violação observada · 10 violação · 20 indeterminado "
               "(BLOQUEIA) · 30 configuração inválida. Começam em 10 para não colidirem com "
               "os 0–5 do pytest, que corre no mesmo pipeline.")
    parser.add_argument("--laudo", type=Path, default=Path("report/summary.json"),
                        help="caminho do summary.json (padrão: report/summary.json)")
    parser.add_argument("--quieto", action="store_true",
                        help="não imprime o motivo; o veredito segue no código de saída")
    args = parser.parse_args(argv)

    laudo, erro = ler(args.laudo)
    if laudo is None:
        print(f"::error::config inválida: {erro}", file=sys.stderr)
        return CONFIG_INVALIDA

    veredito = avaliar(laudo)
    if not args.quieto:
        destino = sys.stderr if veredito.codigo else sys.stdout
        print(f"[{veredito.estado}] {veredito.motivo}", file=destino)
    return veredito.codigo


if __name__ == "__main__":
    raise SystemExit(main())
