"""As âncoras `arquivo:linha` da documentação ainda apontam para o que dizem?

**Por que isto é mecânico agora.** Em três OSs a mesma classe de defeito apareceu
duas vezes: a OS-48 mexeu no `conftest.py` e **quatro de oito** âncoras do
`GUI.md` passaram a mentir — uma delas dizia "a mesma regra da fixture `browser`"
apontando para a docstring de outra fixture, que é a forma mais cara de mentira
porque a frase continua fazendo sentido. A OS-50 deslocou **mais duas**, e só não
passaram porque quem executou foi conferir de propósito. Duas ocorrências em três
OSs não é acidente: é rotina, e rotina se mecaniza.

**Só CONTEÚDO pega deriva.** Conferir que o arquivo existe e que o intervalo cabe
nele é barato e não pega nada: uma âncora deslocada continua existindo e continua
dentro do arquivo — ela só passou a apontar para outra coisa. Por isso o mapa
guarda um FRAGMENTO distintivo (nome de função, chave de configuração, trecho de
identificador) e a guarda cobra que ele ainda esteja no intervalo citado.

Fragmento **curto e distintivo**, nunca a linha inteira: linha inteira transforma
todo ajuste de espaçamento ou de redação em vermelho, e uma guarda que grita por
qualquer coisa é desligada — o defeito que ela existia para pegar volta a passar.

**Cobertura DECLARADA, e é o ponto do desenho.** `data/ancoras.yaml` declara o
estado de **todo** documento: `auditado`, `pendente` (com motivo) ou `congelado`
(com motivo). Documento sem estado declarado REPROVA — doc novo não pode nascer
invisível à guarda, que é como uma guarda parcial vira uma guarda que parece
completa. Os pendentes são contados e impressos em toda execução: cobertura
parcial silenciosa é pior que cobertura nenhuma, porque induz confiança.

**Bidirecional nos auditados**, pelo mesmo motivo das outras guardas da casa:
âncora no documento que não está no mapa reprova (âncora nova entrando sem
conferência), e entrada no mapa sem âncora correspondente reprova (âncora
removida deixando lixo que finge cobertura).

Fora de escopo por decisão: `§seção` e IDs de catálogo (`GUI-PERF-02`). Nem
seção nem ID deslocam quando alguém insere uma linha — o problema que esta guarda
existe para pegar é específico do número de linha.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
RAIZ_REPO = RAIZ.parent
MAPA_PADRAO = RAIZ / "data" / "ancoras.yaml"

# Raízes contra as quais um caminho citado é resolvido, EM ORDEM. Existem porque
# a documentação da casa cita caminhos de várias formas — `ARQUITETURA.md:44` (a
# partir de `docs/`), `report_html.py:382` (a partir de `webqa/`),
# `lgpd/test_terceiros.py:78` (a partir de `checks/`) — e todas são legítimas
# para quem lê. Tratar as três como "arquivo inexistente" e ignorá-las deixaria
# 21 das 91 âncoras da tranche 1 fora da conferência, com a guarda parecendo
# completa. Cobertura que parece completa e não é foi o defeito que esta OS
# nasceu para não repetir.
RAIZES_DE_BUSCA = ("", "webqa-suite", "webqa-suite/docs", "webqa-suite/checks",
                   "webqa-suite/webqa", "webqa-suite/scripts", "webqa-suite/tests",
                   "webqa-suite/fixture_target", "webqa-suite/data")

_EXT = "py|yaml|yml|json|toml|ini|md|sh|cfg|txt"
_CAMINHO = rf"(?:[\w.-]+/)*[\w.-]+\.(?:{_EXT})"
# Duas formas numa varredura só, e a ordem importa: o caminho isolado (sem `:N`)
# também é capturado, porque é ele que dá sentido à âncora RELATIVA que vem
# depois. Em `test_rendering.py | ... (`:30-35`)` o número não diz de qual
# arquivo é — quem lê resolve olhando para trás, e a guarda resolve igual.
# A relativa é reconhecida pela CRASE, não pelos parênteses: a documentação da
# casa a escreve das duas formas — ``(`:30-35`)`` e ``bloco `:5-15` `` — e uma
# regra que exigisse parênteses perderia três das dez relativas do `GUI.md`
# calada. Guarda que perde caso em silêncio é o defeito que esta OS combate.
_TOKEN = re.compile(rf"(?<![\w/.-])({_CAMINHO})(?::(\d+(?:[-,]\d+)*))?"
                    rf"|`:(\d+(?:[-,]\d+)*)`")

ESTADOS = ("auditado", "pendente", "congelado")


@dataclass(frozen=True)
class Ancora:
    """Uma citação `arquivo:linha` encontrada num documento."""

    chave: str                 # como vira chave no mapa: "conftest.py:200-205"
    caminho: str               # resolvido, relativo à raiz do repositório
    linhas: tuple[int, ...]
    linha_no_doc: int
    relativa: bool = False

    def __str__(self) -> str:
        sufixo = " (relativa, resolvida por contexto)" if self.relativa else ""
        return f"{self.chave}{sufixo}"


def linhas_de(spec: str) -> tuple[int, ...]:
    """`"200-205"` → (200..205); `"72,80"` → (72, 80); `"56"` → (56,).

    As três formas existem na documentação da casa e todas são legítimas —
    intervalo para um bloco, lista para dois pontos distantes, número para uma
    linha. Normalizar aqui é o que permite o resto do módulo tratar tudo como
    "conjunto de linhas onde o fragmento pode estar".
    """
    linhas: list[int] = []
    for parte in spec.split(","):
        if "-" in parte:
            inicio, fim = (int(x) for x in parte.split("-", 1))
            linhas.extend(range(inicio, fim + 1))
        else:
            linhas.append(int(parte))
    return tuple(linhas)


def resolver_caminho(citado: str, raiz_repo: Path | None = None) -> str | None:
    """O caminho citado, resolvido contra `RAIZES_DE_BUSCA`. `None` se não existe.

    Primeira raiz que resolve vence, e a ordem de `RAIZES_DE_BUSCA` é a decisão.
    Caminho que não resolve em raiz nenhuma é ignorado pela guarda: é prosa que
    parece caminho (`e.g. app.js:12` num exemplo), e reprovar por causa dela
    faria a guarda cobrar documentação por texto que não é âncora.
    """
    raiz_repo = raiz_repo or RAIZ_REPO
    for prefixo in RAIZES_DE_BUSCA:
        alvo = (raiz_repo / prefixo / citado) if prefixo else (raiz_repo / citado)
        if alvo.is_file():
            return str(alvo.relative_to(raiz_repo))
    return None


def ancoras_de(texto: str, raiz_repo: Path | None = None) -> tuple[Ancora, ...]:
    """Âncoras de um documento, na ordem em que aparecem.

    A âncora relativa (`` (`:30-35`) ``) herda o caminho do último caminho citado
    antes dela — a mesma leitura que uma pessoa faz. Relativa antes de qualquer
    caminho é ignorada: não há o que herdar, e adivinhar seria pior que omitir.
    """
    encontradas: list[Ancora] = []
    ultimo_caminho: str | None = None
    for achado in _TOKEN.finditer(texto):
        citado, spec, spec_relativa = achado.group(1), achado.group(2), achado.group(3)
        linha_no_doc = texto[:achado.start()].count("\n") + 1
        if citado and not spec:
            ultimo_caminho = citado          # só contexto para a próxima relativa
            continue
        alvo = citado or ultimo_caminho
        if alvo is None:
            continue
        resolvido = resolver_caminho(alvo, raiz_repo)
        if resolvido is None:
            continue
        encontradas.append(Ancora(
            chave=f"{alvo}:{spec or spec_relativa}",
            caminho=resolvido,
            linhas=linhas_de(spec or spec_relativa),
            linha_no_doc=linha_no_doc,
            relativa=citado is None,
        ))
        if citado:
            ultimo_caminho = citado
    return tuple(encontradas)


def _conteudo(caminho: str, raiz_repo: Path) -> list[str]:
    return (raiz_repo / caminho).read_text(encoding="utf-8", errors="replace").splitlines()


def problema_da_ancora(ancora: Ancora, fragmento: str, doc: str,
                       raiz_repo: Path) -> str | None:
    """A âncora ainda aponta para o que diz? `None` quando sim.

    A mensagem instrui o conserto do PAR — qual documento cita, qual fragmento
    procurar — porque quem lê o erro precisa decidir entre duas coisas
    diferentes: o alvo se moveu (conserta-se o número) ou o alvo sumiu
    (conserta-se a frase). Um erro que só diz "âncora errada" deixa essa escolha
    para adivinhação.
    """
    linhas = _conteudo(ancora.caminho, raiz_repo)
    fora = [n for n in ancora.linhas if n > len(linhas)]
    if fora:
        return (f"{doc} cita `{ancora}` (linha {ancora.linha_no_doc} do doc), mas "
                f"{ancora.caminho} tem só {len(linhas)} linhas — o intervalo passa do "
                f"fim do arquivo. Releia o trecho e reescreva a âncora.")
    trecho = "\n".join(linhas[n - 1] for n in ancora.linhas)
    if fragmento in trecho:
        return None
    return (f"{doc} cita `{ancora}` (linha {ancora.linha_no_doc} do doc) esperando "
            f"encontrar {fragmento!r} ali, e o que está em {ancora.caminho} naquelas "
            f"linhas é outra coisa. Duas correções possíveis, e a escolha é de quem "
            f"lê: se o alvo apenas se DESLOCOU, procure {fragmento!r} no arquivo e "
            f"atualize o número; se o alvo SUMIU, a frase do documento é que precisa "
            f"mudar. Atualizar o mapa sem reler o documento reintroduz a mentira.")


def problemas_do_documento(doc: str, mapa: dict, raiz_repo: Path | None = None) -> list[str]:
    """Guarda BIDIRECIONAL de um documento auditado.

    Os dois lados existem por motivos diferentes e nenhum cobre o outro: sem o
    primeiro, âncora nova entra sem passar por conferência nenhuma; sem o
    segundo, âncora removida deixa entrada no mapa fingindo cobertura que já não
    tem objeto.
    """
    raiz_repo = raiz_repo or RAIZ_REPO
    texto = (raiz_repo / doc).read_text(encoding="utf-8")
    ancoras = {a.chave: a for a in ancoras_de(texto, raiz_repo)}
    problemas = []
    for chave, ancora in ancoras.items():
        if chave not in mapa:
            problemas.append(
                f"{doc} cita `{chave}` (linha {ancora.linha_no_doc}) e o mapa não "
                f"conhece essa âncora. Releia o alvo e declare o fragmento distintivo "
                f"em data/ancoras.yaml — âncora nova sem conferência é como as quatro "
                f"do GUI.md entraram.")
    for chave in mapa:
        if chave not in ancoras:
            problemas.append(
                f"data/ancoras.yaml declara `{chave}` para {doc}, e o documento não "
                f"cita mais essa âncora. Apague a entrada: mapa com entrada órfã "
                f"conta cobertura que não existe mais.")
    for chave, ancora in ancoras.items():
        if chave in mapa:
            falha = problema_da_ancora(ancora, str(mapa[chave]), doc, raiz_repo)
            if falha:
                problemas.append(falha)
    return problemas


def carregar(caminho: str | Path | None = None) -> dict:
    dados = yaml.safe_load(Path(caminho or MAPA_PADRAO).read_text(encoding="utf-8")) or {}
    return dados.get("documentos") or {}


def documentos_do_repo(raiz_repo: Path | None = None) -> list[str]:
    """Todo `.md` sob `webqa-suite/docs/`, relativo à raiz do repositório."""
    raiz_repo = raiz_repo or RAIZ_REPO
    base = raiz_repo / "webqa-suite" / "docs"
    return sorted(str(p.relative_to(raiz_repo)) for p in base.rglob("*.md"))


def problemas_de_cobertura(declarados: dict, existentes: list[str]) -> list[str]:
    """Todo documento tem estado declarado, e todo estado declarado é válido."""
    problemas = []
    for doc in existentes:
        if doc not in declarados:
            problemas.append(
                f"{doc} não tem estado declarado em data/ancoras.yaml. Declare "
                f"`auditado`, `pendente` (com motivo) ou `congelado` (com motivo) — "
                f"documento sem estado nasce invisível à guarda, e é assim que uma "
                f"cobertura parcial passa por completa.")
    for doc, entrada in declarados.items():
        estado = (entrada or {}).get("estado")
        if estado not in ESTADOS:
            problemas.append(
                f"{doc} declara estado {estado!r}, que não é um de {ESTADOS}.")
        elif estado != "auditado" and not (entrada or {}).get("motivo", "").strip():
            problemas.append(
                f"{doc} está {estado!r} sem motivo escrito. Estado sem motivo é uma "
                f"decisão que ninguém consegue revisar depois.")
    return problemas


def aferir(declarados: dict, raiz_repo: Path | None = None) -> tuple[list[str], dict]:
    """(problemas, placar). O placar sai SEMPRE, mesmo sem problema nenhum."""
    raiz_repo = raiz_repo or RAIZ_REPO
    existentes = documentos_do_repo(raiz_repo)
    problemas = problemas_de_cobertura(declarados, existentes)
    placar = {"auditados": [], "pendentes": [], "congelados": [], "ancoras": 0}
    for doc, entrada in sorted(declarados.items()):
        estado = (entrada or {}).get("estado")
        if estado == "auditado":
            mapa = (entrada or {}).get("ancoras") or {}
            placar["auditados"].append(doc)
            placar["ancoras"] += len(mapa)
            problemas.extend(problemas_do_documento(doc, mapa, raiz_repo))
        elif estado in ("pendente", "congelado"):
            placar[estado + "s"].append(doc)
    return problemas, placar


def resumo(placar: dict) -> str:
    """O placar, impresso em TODA execução.

    Pendente silencioso é o modo de falha desta guarda: ela fica verde, e o verde
    é lido como "a documentação está conferida" quando significa "a parte que
    alguém conferiu está conferida". O número na tela é o que impede essa leitura.
    """
    return (f"âncoras: {placar['ancoras']} conferidas em "
            f"{len(placar['auditados'])} doc(s) auditado(s); "
            f"{len(placar['pendentes'])} pendente(s), "
            f"{len(placar['congelados'])} congelado(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mapa", type=Path, default=None)
    args = parser.parse_args(argv)

    declarados = carregar(args.mapa)
    problemas, placar = aferir(declarados)
    print(resumo(placar))
    for doc in placar["pendentes"]:
        print(f"  pendente: {doc}")
    if problemas:
        for p in problemas:
            print(f"::error::{p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
