"""Autoprova de mordida POR RELEASE: as travas desta régua ainda mordem?

**O que já existia, e o que faltava.** A mordida existia em duas formas maduras —
o **contrato 1:1** (`fixture_target/esperado.json`: os nodeids que DEVEM reprovar
contra o alvo fabricado, conferidos em todo push) e a **mutação escopada**
(`scripts/mutar.py`, noturno). O que faltava era orquestração **por release**, com
o resultado carimbado no manifesto: uma régua verde cujas travas não mordem é
indistinguível de uma régua verde, e a release é exatamente o momento em que
alguém do outro lado passa a confiar nela sem poder olhar.

**O escopo, e a navalha que o define.** Entram:

* os **`devem_falhar`** do contrato 1:1 — cada um é uma violação PLANTADA no alvo
  fabricado, e a mordida é o check reprovar por causa dela;
* a **aferição do smoke** (`afere_smoke_gui`) nas duas direções — a guarda precisa
  aprovar o laudo que exerceu de verdade E reprovar o "verde por ausência". Guarda
  que só sabe aprovar não é guarda.

Não entram, e a recusa é declarada e não silenciosa: toda entrada de
`fora_do_contrato` vira `declarado-sem-mordida` **com o motivo já escrito no
esperado.json**. Exigir mordida determinística delas violaria a navalha do
contrato — rede externa, origem declarada (`WEBQA_ORIGEM`), binário de engine
instalado e tempo são AMBIENTE, e uma mordida que depende do ambiente reprova por
ambiente, nunca por regressão. É a propriedade que o contrato 1:1 existe para ter.

**Por que não o `audit_mutations` do molde — o veredito, escrito.** Comparados:

* **o que muta** — `mutar.py` mexe na **AST** de Python (operadores de
  comparação, booleanos, `not`, constantes); o motor do molde mexe em **texto e
  caminhos** (apagar linha, apagar padrão, substituir texto, remover arquivo).
* **a quem pergunta** — `mutar.py` pergunta *"minhas ASSERÇÕES são fortes?"*; o
  motor pergunta *"esta trava DECLARADA morde?"*.
* **sobre o quê** — um age no código do motor; o outro, no artefato declarado
  (uma ficha, um schema, um documento).

**Veredito: CONVIVEM, e não há peça compartilhada a extrair.** As duas respondem a
perguntas diferentes sobre objetos diferentes, e a interseção do código é vazia —
um transforma árvore sintática, o outro edita bytes. Extrair "a peça comum" seria
inventar uma abstração sobre duas coisas que só compartilham a palavra *mutação*.
O motor do molde tem lugar aqui no dia em que esta suíte tiver travas DECLARADAS
em arquivo (uma ficha, um schema) — hoje ela não tem: as travas são asserções, e
asserção se prova mutando código.

**E a mutação escopada continua escopada.** Rodar mutação nos 3.073 statements do
repositório é recusa registrada do fornecedor: é cara e não responde nada que o
escopo da superfície de segurança já não responda melhor. Esta autoprova NÃO chama
`mutar.py` — ela orquestra o que é determinístico por release; a mutação segue no
noturno, onde o custo cabe.

Uso:
    python scripts/autoprova.py                 # roda o escopo, emite report/autoprova.json
    python scripts/autoprova.py --saida X.json

Saída: 0 todas as mordidas do escopo morderam · 1 alguma não mordeu · 2 não foi
possível provar (sem navegador, alvo não subiu). O código 2 existe porque *"não
consegui provar"* e *"provei que não morde"* pedem reações diferentes — e a única
coisa que as duas NÃO podem produzir é uma release aprovada.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - argv fixo, sem shell; só este interpretador
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONTRATO = RAIZ / "fixture_target" / "esperado.json"

MORDERAM = 0
NAO_MORDERAM = 1
INDETERMINADO = 2


def carregar_contrato(caminho: Path | None = None) -> dict:
    return json.loads((caminho or CONTRATO).read_text(encoding="utf-8"))


def selecao_do_contrato(contrato: dict) -> str:
    """A seleção `-m` vem do PRÓPRIO contrato, nunca digitada aqui.

    Contrato e execução divergindo é a forma mais silenciosa de a autoprova provar
    outra coisa que não o que promete provar.
    """
    return contrato["escopo"].split("-m", 1)[1].strip().strip('"')


def morderam(contrato: dict, resultados: list[dict]) -> tuple[list[str], list[str]]:
    """(morderam, não morderam) entre os `devem_falhar` do contrato 1:1.

    Função pura sobre os resultados já lidos: é o que permite exercitar a
    sabotagem sem subir alvo nenhum.
    """
    por_id = {r["test"]: r.get("estado") or r.get("outcome") for r in resultados}
    esperados = list(contrato["devem_falhar"])
    mordidas = [n for n in esperados if por_id.get(n) == "failed"]
    return mordidas, [n for n in esperados if n not in mordidas]


def declarados_sem_mordida(contrato: dict) -> list[dict]:
    """`fora_do_contrato` inteiro, COM O MOTIVO — nunca uma contagem.

    O motivo é o que separa "não provamos" de "decidimos não provar, e eis por
    quê". Uma lista de nodeids sem motivo seria a mesma lacuna que o contrato
    inteiro existe para não ter.
    """
    return [{"nodeid": nodeid, "motivo": motivo}
            for nodeid, motivo in sorted(contrato["fora_do_contrato"].items())]


# ---------------------------------------------------------------- smoke de GUI

def _laudo_gui(**contagem) -> dict:
    return {"by_dimension": {"gui": contagem}}


def direcoes_do_smoke() -> dict[str, bool]:
    """A guarda do smoke morde nas DUAS direções?

    Aprovar o laudo que exerceu de verdade não prova nada sozinho: uma guarda que
    devolve sempre "ok" faria exatamente isso. As três direções são exercidas sobre
    laudos fabricados porque duas delas não dão para produzir num CI de verdade sem
    quebrar o CI de propósito.
    """
    sys.path.insert(0, str(RAIZ))
    from scripts.afere_smoke_gui import aferir

    return {
        # exerceu: passou de verdade contra a página conforme ⇒ NÃO reprova
        "conforme_aprova": aferir(_laudo_gui(passed=12, failed=0, skipped=0)) == "",
        # verde por ausência: tudo pulado (sem Chromium) ⇒ REPROVA
        "verde_por_ausencia_reprova": bool(aferir(_laudo_gui(passed=0, failed=0, skipped=12))),
        # falso positivo: reprovou a página CONFORME ⇒ REPROVA
        "falso_positivo_reprova": bool(aferir(_laudo_gui(passed=8, failed=1, skipped=0))),
        # dimensão ausente do laudo: nem coletado ⇒ REPROVA
        "dimensao_ausente_reprova": bool(aferir({"by_dimension": {}})),
    }


# ---------------------------------------------------------------- orquestração

def rodar_contrato(contrato: dict, raiz: Path | None = None) -> tuple[list[dict], str]:
    """(resultados, motivo da indeterminação). Sobe o alvo fabricado e mede.

    Subprocesso com `WEBQA_REPORT_DIR` próprio, pela mesma razão de
    `tests/test_alvo_fixture.py`: um pytest dentro de outro compartilharia o estado
    do plugin de relatório e sobrescreveria o artefato da execução externa.
    """
    raiz = raiz or RAIZ
    sys.path.insert(0, str(raiz))
    try:
        import playwright  # noqa: F401
    except ImportError:
        return [], ("Playwright ausente: as violações plantadas de `gui` só são "
                    "observáveis com navegador, e sem ele a autoprova não prova.")
    import tempfile

    from fixture_target.servir import AlvoFixture

    with tempfile.TemporaryDirectory(prefix="webqa-autoprova-") as tmp, AlvoFixture() as alvo:
        env = {**os.environ, "WEBQA_TARGET_URL": alvo.url, "WEBQA_REPORT_DIR": tmp,
               "NO_PROXY": "*", "no_proxy": "*"}
        proc = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", "-m", selecao_do_contrato(contrato),
             "-p", "no:cacheprovider", "-q"],
            cwd=str(raiz), env=env, capture_output=True, text=True, timeout=1800)
        laudo = Path(tmp) / "summary.json"
        if not laudo.exists():
            return [], f"a execução do contrato não deixou laudo:\n{proc.stdout[-1500:]}"
        dados = json.loads(laudo.read_text(encoding="utf-8"))

    sem_navegador = [r for r in dados["results"]
                     if r.get("browser") and r.get("estado") == "skipped"
                     and "Chromium indispon" in (r.get("detail") or "")]
    if sem_navegador:
        return [], (f"Chromium indisponível ({len(sem_navegador)} checks pulados): as violações "
                    f"plantadas de `gui` não foram exercidas, e contar as demais como 'todas "
                    f"morderam' seria a autoprova mentindo por omissão.")
    return dados["results"], ""


def montar(contrato: dict, resultados: list[dict], indeterminado: str) -> dict:
    mordidas, faltantes = morderam(contrato, resultados)
    direcoes = direcoes_do_smoke()
    total = len(contrato["devem_falhar"])
    aprovada = (not indeterminado) and not faltantes and all(direcoes.values())
    return {
        "escopo": {
            "devem_falhar": {"total": total, "morderam": len(mordidas),
                             "nao_morderam": faltantes},
            "smoke_gui": direcoes,
        },
        "declarado_sem_mordida": declarados_sem_mordida(contrato),
        "indeterminado": indeterminado,
        "aprovada": aprovada,
    }


def imprimir(relatorio: dict) -> None:
    d = relatorio["escopo"]["devem_falhar"]
    print(f"autoprova: {d['morderam']}/{d['total']} mordidas do contrato 1:1 reprovando; "
          f"smoke de GUI {sum(relatorio['escopo']['smoke_gui'].values())}/"
          f"{len(relatorio['escopo']['smoke_gui'])} direções; "
          f"{len(relatorio['declarado_sem_mordida'])} declarado(s)-sem-mordida com motivo.")
    for nodeid in d["nao_morderam"]:
        print(f"::error::não mordeu: {nodeid} — a violação segue plantada no alvo fabricado e o "
              f"check deixou de detectá-la, ou a violação sumiu sem o contrato ser atualizado.")
    for nome, ok in relatorio["escopo"]["smoke_gui"].items():
        if not ok:
            print(f"::error::a guarda do smoke não morde na direção `{nome}` — guarda que só sabe "
                  f"aprovar aprova qualquer coisa.")
    if relatorio["indeterminado"]:
        print(f"::error::não foi possível provar: {relatorio['indeterminado']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--saida", type=Path, default=RAIZ / "report" / "autoprova.json")
    parser.add_argument("--contrato", type=Path, default=CONTRATO)
    args = parser.parse_args(argv)

    contrato = carregar_contrato(args.contrato)
    resultados, indeterminado = rodar_contrato(contrato)
    relatorio = montar(contrato, resultados, indeterminado)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    imprimir(relatorio)
    if relatorio["indeterminado"]:
        return INDETERMINADO
    return MORDERAM if relatorio["aprovada"] else NAO_MORDERAM


if __name__ == "__main__":
    raise SystemExit(main())
