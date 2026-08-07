"""O caminho de instalação DECLARADO do padrão — lido do README, nunca restatado.

**Por que existe.** O `README.md` é a página do wheel (`project.readme`) e é onde
quem adota o padrão procura como instalá-lo. Até aqui ele dizia `pip install
webqa-suite`, que **não resolve**: o pacote não está em índice nenhum, e o
`pyproject.toml` não vive na raiz do repositório — vive em `webqa-suite/`. As duas
coisas juntas fazem qualquer instalação ingênua falhar com "projeto inválido",
mandando quem instala procurar defeito no lugar errado.

**Por que como script, e não como constante.** Se o caminho fosse uma string neste
arquivo, existiriam DOIS caminhos declarados — o do README, que as pessoas leem, e
o do código, que a máquina executa — e a primeira divergência entre eles seria
justamente a que ninguém veria. Aqui o README é a fonte e este módulo é só o
leitor: `tests/test_empacotamento.py` confere a FORMA do que foi lido, e o job
`instalacao-declarada` do CI EXECUTA o que foi lido. É a mesma lição do
`afere_smoke_gui.py` — guarda em script próprio é guarda que também tem teste.

**Fora do wheel de propósito.** Isto é ferramenta do repositório, não biblioteca:
quem já instalou o pacote não precisa da instrução para instalá-lo.

Uso:
    python scripts/caminho_de_instalacao.py
    python scripts/caminho_de_instalacao.py --local . --ref "$(git rev-parse HEAD)"

Somente stdlib.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RAIZ_REPO = RAIZ.parent
README_PADRAO = RAIZ / "README.md"

# A linha canônica do README. Exige a forma PEP 508 de referência direta INTEIRA —
# nome, `git+`, origem, `@ref` e `#subdirectory=` —, e é essa exigência que torna
# a guarda útil: um README que perdesse só o fragmento do subdiretório continuaria
# parecendo uma instrução de instalação correta para quem lê de relance.
_LINHA = re.compile(
    r'^pip install "(?P<spec>[^"]+)"\s*$', re.MULTILINE)

_SPEC = re.compile(
    r"^(?P<nome>[A-Za-z0-9][A-Za-z0-9._-]*) @ "
    r"git\+(?P<origem>https://github\.com/(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+))"
    r"@(?P<ref>[^#]+)"
    r"#subdirectory=(?P<subdiretorio>[A-Za-z0-9._/-]+)$")


@dataclass(frozen=True)
class Caminho:
    """As partes do caminho declarado. `spec` é o que se entrega ao `pip`."""

    spec: str
    nome: str
    origem: str
    repo: str
    ref: str
    subdiretorio: str


def declarado(readme: str | Path | None = None) -> Caminho:
    """O caminho de instalação do README, decomposto — ou `ValueError`.

    Recusa AMBIGUIDADE: dois `pip install "..."` no README seriam dois caminhos
    declarados, e um leitor escolheria por proximidade enquanto a guarda escolheria
    por ordem. "Qual dos dois é o caminho?" não pode ter resposta implícita.
    """
    texto = Path(readme or README_PADRAO).read_text(encoding="utf-8")
    specs = [m.group("spec") for m in _LINHA.finditer(texto)]
    if not specs:
        raise ValueError(
            'o README não declara caminho de instalação: nenhuma linha `pip install "…"`. '
            "Sem ela, quem adota o padrão tem de adivinhar a origem e o subdiretório — e a "
            "adivinhação falha com 'projeto inválido', que manda procurar defeito no "
            "lugar errado.")
    if len(specs) > 1:
        raise ValueError(
            f"o README declara {len(specs)} caminhos de instalação ({specs}). Um caminho "
            f"declarado é uma decisão; dois são uma pergunta que o leitor responde por "
            f"proximidade e a guarda responde por ordem.")
    m = _SPEC.match(specs[0])
    if not m:
        raise ValueError(
            f"o caminho declarado não é uma referência direta PEP 508 completa: {specs[0]!r}. "
            f"Esperado `<nome> @ git+https://github.com/<dono>/<repo>@<ref>#subdirectory=<dir>`. "
            f"Sem o fragmento `#subdirectory=`, o pip procura o pyproject.toml na raiz do "
            f"repositório — onde ele não está.")
    return Caminho(spec=specs[0], **m.groupdict())


def com_ref(caminho: Caminho, ref: str) -> str:
    """O MESMO caminho, apontando para outra referência do MESMO repositório.

    É o que o CI usa: a tag declarada vira o commit sob teste, e tudo o mais —
    nome, origem, subdiretório, a forma da referência direta — segue vindo do
    README. Se o job pudesse montar a string sozinho, ele passaria a provar a si
    mesmo, e o README poderia perder o `#subdirectory=` sem nada ficar vermelho.
    """
    return (f"{caminho.nome} @ git+{caminho.origem}@{ref}"
            f"#subdirectory={caminho.subdiretorio}")


def local(caminho: Caminho, raiz: str | Path, ref: str) -> str:
    """O mesmo caminho contra um clone LOCAL — a reprodução offline do job.

    `file://localhost/…` e não `file:///…`: a forma com autoridade vazia é URL
    inválida para o validador de referência direta do `packaging`, e o `pip` a
    rejeita com *"It looks like a path"* — mensagem que manda procurar defeito no
    argumento em vez de na forma da URL. `localhost` é a autoridade que a RFC 8089
    prevê exatamente para este caso.
    """
    return (f"{caminho.nome} @ git+file://localhost{Path(raiz).resolve()}@{ref}"
            f"#subdirectory={caminho.subdiretorio}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--readme", type=Path, default=README_PADRAO)
    parser.add_argument("--local", type=Path,
                        help="reescreve a origem para este clone local (git+file://localhost)")
    parser.add_argument("--ref",
                        help="usa esta referência (commit/tag) no lugar da declarada")
    args = parser.parse_args(argv)
    try:
        caminho = declarado(args.readme)
    except ValueError as erro:
        print(f"caminho de instalação: {erro}", file=sys.stderr)
        return 1
    if args.local:
        print(local(caminho, args.local, args.ref or "HEAD"))
    elif args.ref:
        print(com_ref(caminho, args.ref))
    else:
        print(caminho.spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
