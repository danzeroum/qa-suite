"""Todo coletor `JS_*` de `webqa/` é executado por algum check? (OS-52)

**O defeito que esta guarda existe para pegar**, encontrado na própria OS-52:
`webqa/i18n.py::JS_PSEUDO_LOCALIZAR` entrou em `main` completo, comentado e
testado — e **nenhum check o executava**. Não era verde falso (não havia check
para ficar verde); era pior de um jeito silencioso: quem lesse o módulo suporia
que a suíte mede RTL, porque o instrumento está lá. A prosa promete o que
nenhuma execução cumpre.

É a mesma classe que `tests/test_config.py::test_todo_orcamento_de_gui_e_lido_por_algum_check`
policia nos limiares — "a garantia existe, a ligação não" —, e que não tinha
equivalente para instrumento.

**Por que só `JS_*`, e não todo símbolo público.** Medido antes de decidir: o
critério amplo ("símbolo público de `webqa/` sem consumidor fora do próprio
módulo") acusa **182 de 404** símbolos. Guarda que acusa 45% do código é
decoração — ninguém age sobre ela, e a allowlist precisaria de 182 entradas com
motivo, o que é a mesma coisa que não ter guarda. O recorte por `JS_*` acusa
**1 de 13**, e o 1 é o defeito real.

O recorte não é arbitrário: um `JS_` é um coletor feito para **rodar contra um
navegador**. Constante, dataclass e função pura existem para ser compostas e
testadas por unidade, e ter só teste é destino legítimo delas. Um coletor que
nenhum check roda não tem destino nenhum.

`tests/` NÃO conta como consumidor, e é o ponto: um coletor coberto só por teste
de unidade continua sendo um instrumento que a suíte nunca aponta para um alvo.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
ALLOWLIST_PADRAO = RAIZ / "data" / "simbolos.yaml"

PREFIXO = "JS_"
# Onde um coletor pode ser CONSUMIDO. `tests/` está fora de propósito.
# `webqa/` conta porque um coletor pode compor outro, e a cadeia termina num
# check — o que a guarda cobra é que exista cadeia, não que ela tenha um elo.
PASTAS_CONSUMIDORAS = ("checks", "scripts", "fixture_target", "webqa")
ARQUIVOS_CONSUMIDORES = ("conftest.py",)


def coletores_de(raiz: Path | None = None) -> dict[str, str]:
    """`{"modulo.py::JS_X": "modulo.py"}` — todo `JS_*` de `webqa/`."""
    raiz = raiz or RAIZ
    achados: dict[str, str] = {}
    for modulo in sorted((raiz / "webqa").glob("*.py")):
        try:
            arvore = ast.parse(modulo.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for no in arvore.body:
            if not isinstance(no, ast.Assign):
                continue
            for alvo in no.targets:
                if isinstance(alvo, ast.Name) and alvo.id.startswith(PREFIXO):
                    achados[f"{modulo.name}::{alvo.id}"] = modulo.name
    return achados


def _fontes(raiz: Path) -> dict[str, str]:
    fontes: dict[str, str] = {}
    for pasta in PASTAS_CONSUMIDORAS:
        for caminho in (raiz / pasta).rglob("*.py"):
            fontes[str(caminho.relative_to(raiz))] = caminho.read_text(encoding="utf-8")
    for nome in ARQUIVOS_CONSUMIDORES:
        caminho = raiz / nome
        if caminho.is_file():
            fontes[nome] = caminho.read_text(encoding="utf-8")
    return fontes


def _nomes_usados(fonte: str) -> set[str]:
    """Identificadores REFERENCIADOS no código — nunca os citados em prosa.

    Por AST, e a razão é um caso real desta própria OS: a primeira versão
    procurava o símbolo por texto, e a guarda passou a se enxergar como
    consumidora porque o docstring dela CITA `JS_PSEUDO_LOCALIZAR` ao explicar o
    defeito. A documentação do defeito escondeu o defeito.

    É a distinção que a casa já faz em `tests/test_fase_c_travada.py`: docstring
    e comentário são livres, porque **explicar não é fazer**. Aqui vale ao
    contrário e pelo mesmo motivo — citar não é executar.
    """
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return set()
    usados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            usados.add(no.id)
        elif isinstance(no, ast.Attribute):
            usados.add(no.attr)
        elif isinstance(no, ast.ImportFrom):
            usados.update(a.name for a in no.names)
    return usados


def consumidores_de(chave: str, fontes: dict[str, str]) -> tuple[str, ...]:
    """Quem REFERENCIA este símbolo em código, tirando o arquivo que o define."""
    modulo, simbolo = chave.split("::", 1)
    return tuple(sorted(
        nome for nome, fonte in fontes.items()
        if not nome.endswith(f"webqa/{modulo}") and simbolo in _nomes_usados(fonte)))


def carregar_allowlist(caminho: str | Path | None = None) -> dict[str, str]:
    dados = yaml.safe_load(Path(caminho or ALLOWLIST_PADRAO).read_text(encoding="utf-8")) or {}
    return dados.get("sem_consumidor") or {}


def problemas(raiz: Path | None = None, allowlist: dict | None = None) -> tuple[list[str], dict]:
    """(problemas, placar). Allowlist SEM motivo reprova como se não existisse."""
    raiz = raiz or RAIZ
    allowlist = carregar_allowlist() if allowlist is None else allowlist
    fontes = _fontes(raiz)
    coletores = coletores_de(raiz)
    achados, orfaos, dispensados = [], [], []
    for chave in sorted(coletores):
        if consumidores_de(chave, fontes):
            continue
        motivo = str(allowlist.get(chave) or "").strip()
        if not motivo:
            orfaos.append(chave)
            achados.append(
                f"{chave} é um coletor que NENHUM check executa. Ou nasce o check que o "
                f"aponta para um alvo, ou o coletor sai de webqa/ — instrumento que a "
                f"suíte nunca usa faz a prosa prometer uma medição que não acontece. "
                f"Se a espera for deliberada, declare o motivo em data/simbolos.yaml.")
        else:
            dispensados.append(chave)
    for chave in allowlist:
        if chave not in coletores:
            achados.append(
                f"data/simbolos.yaml dispensa {chave}, que não existe mais em webqa/. "
                f"Apague a entrada: dispensa órfã esconde a próxima de verdade.")
        elif not str(allowlist[chave] or "").strip():
            achados.append(f"{chave} está dispensado SEM motivo escrito em data/simbolos.yaml.")
    return achados, {"coletores": len(coletores), "orfaos": orfaos,
                     "dispensados": dispensados}


def resumo(placar: dict) -> str:
    return (f"coletores JS_ em webqa/: {placar['coletores']} — "
            f"{len(placar['orfaos'])} sem check que os execute, "
            f"{len(placar['dispensados'])} dispensado(s) com motivo.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allowlist", type=Path, default=None)
    args = parser.parse_args(argv)
    allow = carregar_allowlist(args.allowlist)
    achados, placar = problemas(allowlist=allow)
    print(resumo(placar))
    for chave in placar["dispensados"]:
        print(f"  dispensado: {chave}")
    if achados:
        for a in achados:
            print(f"::error::{a}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
