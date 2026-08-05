"""A linha de base visual — onde ela mora, o que ela declara, e o que ela NÃO é.

Regressão visual só vale alguma coisa se a referência for confiável, e uma
referência é confiável quando três perguntas têm resposta escrita: **de onde
veio**, **quando**, e **por que está assim**. Por isso cada PNG versionado tem
um manifesto ao lado, e por isso regravar sem atualizar o manifesto reprova.

**Identidade do artefato: `pagina|viewport|tema`.** É o que determina o que a
captura mostra. Sem os três no nome, a referência de `mobile` acaba comparada
com a captura de `desktop` e o diff acusa a página inteira — com a causa
escondida atrás de "94% dos blocos divergentes".

**Só página FABRICADA é versionada.** É a primeira das três vias de
`docs/GUI.md §3.4`, e a única que cabe no Git: `report/` nunca é versionado
(carrega host e erro do alvo), e captura de alvo real não é versionável por
causa do R19 — pixel não passa pela borda de sanitização. Referência de alvo
real vive fora da árvore, sob `WEBQA_GUI_BASELINE_DIR`.

**Referência ausente é SKIP com instrução, nunca PASS.** No primeiro run não há
o que comparar, e um check que "passa" nessa situação anuncia estabilidade que
ninguém mediu — o verde indistinguível do verde legítimo, mais uma vez.

Somente stdlib.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REFERENCIAS_FABRICADAS = RAIZ / "fixture_target" / "baseline"
ENV_DIRETORIO = "WEBQA_GUI_BASELINE_DIR"

# Campos sem os quais o manifesto não descreve a procedência. `motivo` é
# obrigatório porque uma referência sem explicação é indistinguível de uma
# referência esquecida — e é justamente a que ninguém ousa regravar.
CAMPOS_DO_MANIFESTO = ("sha256", "engine", "viewport", "tema", "pagina",
                       "gravado_em", "motivo")


@dataclass(frozen=True)
class Artefato:
    """Onde a referência de uma variação mora, e o que ela declara."""

    pagina: str
    viewport: str
    tema: str = "light"

    @property
    def identidade(self) -> str:
        return f"{self.pagina}|{self.viewport}|{self.tema}"

    @property
    def nome(self) -> str:
        seguro = self.pagina.strip("/").replace("/", "-").replace("#", "--") or "raiz"
        return f"{seguro}__{self.viewport}__{self.tema}"


def diretorio(ambiente=None) -> Path:
    """Onde as referências ficam. Fora da árvore quando declarado."""
    ambiente = os.environ if ambiente is None else ambiente
    declarado = (ambiente.get(ENV_DIRETORIO) or "").strip()
    return Path(declarado) if declarado else REFERENCIAS_FABRICADAS


def caminho_png(artefato: Artefato, base: Path | None = None) -> Path:
    return (base or diretorio()) / f"{artefato.nome}.png"


def caminho_manifesto(artefato: Artefato, base: Path | None = None) -> Path:
    return (base or diretorio()) / f"{artefato.nome}.json"


def motivo_de_pular(artefato: Artefato, base: Path | None = None) -> str:
    """Referência ausente → skip com a instrução exata, nunca PASS."""
    return (f"Sem linha de base visual para {artefato.identidade} "
            f"({caminho_png(artefato, base)}). Primeira execução não tem o que "
            "comparar, e passar aqui anunciaria estabilidade que ninguém mediu. "
            "Grave com `make referencia-visual`.")


def existe(artefato: Artefato, base: Path | None = None) -> bool:
    return caminho_png(artefato, base).exists()


def carregar(artefato: Artefato, base: Path | None = None) -> bytes:
    return caminho_png(artefato, base).read_bytes()


# ---------- Manifesto ----------


def manifesto_de(artefato: Artefato, png: bytes, *, engine: str, gravado_em: str,
                 motivo: str) -> dict:
    """O manifesto de procedência. `gravado_em` é injetado, não lido do relógio:
    é o que torna a função pura e o teste determinístico."""
    return {
        "sha256": hashlib.sha256(png).hexdigest(),
        "engine": engine,
        "viewport": artefato.viewport,
        "tema": artefato.tema,
        "pagina": artefato.pagina,
        "gravado_em": gravado_em,
        "motivo": motivo,
    }


def ler_manifesto(artefato: Artefato, base: Path | None = None) -> dict:
    caminho = caminho_manifesto(artefato, base)
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def problemas_do_manifesto(artefato: Artefato, base: Path | None = None) -> list[str]:
    """O que falta para a procedência estar declarada.

    **Regravar sem atualizar o manifesto reprova**, e o mecanismo é o `sha256`:
    o manifesto descreve UM arquivo, e um PNG novo com manifesto velho é
    exatamente a situação em que ninguém sabe mais de onde a referência veio.
    """
    caminho = caminho_manifesto(artefato, base)
    if not caminho.exists():
        return [f"manifesto ausente: {caminho}"]
    dados = ler_manifesto(artefato, base)
    faltando = [campo for campo in CAMPOS_DO_MANIFESTO
                if not str(dados.get(campo) or "").strip()]
    problemas = [f"campo obrigatório vazio no manifesto: {campo}" for campo in faltando]
    if not existe(artefato, base):
        return problemas + [f"manifesto sem PNG correspondente: {caminho_png(artefato, base)}"]
    atual = hashlib.sha256(carregar(artefato, base)).hexdigest()
    if dados.get("sha256") and dados["sha256"] != atual:
        problemas.append(
            f"o PNG mudou e o manifesto não: sha256 declarado {dados['sha256'][:12]}…, "
            f"arquivo {atual[:12]}…. Regrave com `make referencia-visual`, que "
            "reescreve os dois — manifesto velho descrevendo imagem nova é uma "
            "procedência que mente")
    return problemas


def gravar(artefato: Artefato, png: bytes, *, engine: str, gravado_em: str,
           motivo: str, base: Path | None = None) -> Path:
    """Grava PNG e manifesto JUNTOS. Não há caminho que grave só um."""
    destino = base or diretorio()
    destino.mkdir(parents=True, exist_ok=True)
    caminho_png(artefato, destino).write_bytes(png)
    manifesto = manifesto_de(artefato, png, engine=engine, gravado_em=gravado_em,
                             motivo=motivo)
    caminho_manifesto(artefato, destino).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho_png(artefato, destino)


# ---------- Páginas do contrato visual ----------


@dataclass(frozen=True)
class PaginaVisual:
    """Uma variação declarada em `data/gui-perfis.yaml::visual.paginas`."""

    caminho: str
    viewport: str
    regravar: bool = True
    componentes: tuple[str, ...] = ()

    def artefato(self, componente: str = "") -> Artefato:
        pagina = f"{self.caminho}#{componente}" if componente else self.caminho
        return Artefato(pagina=pagina, viewport=self.viewport)


def carregar_paginas(caminho=None) -> tuple[PaginaVisual, ...]:
    """As variações do contrato visual, de `data/gui-perfis.yaml`.

    Lista vazia é estado legítimo (o check pula dizendo isso), e não erro: um
    repositório pode não querer contrato visual nenhum. O que não pode é a
    lista existir e ninguém lê-la — por isso há teste provando a ligação.
    """
    import yaml

    from webqa.viewports import PERFIS_PADRAO
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    brutas = (dados.get("visual") or {}).get("paginas") or []
    return tuple(
        PaginaVisual(
            caminho=str(b.get("caminho") or "/"),
            viewport=str(b.get("viewport") or "desktop"),
            regravar=bool(b.get("regravar", True)),
            componentes=tuple(str(c) for c in (b.get("componentes") or ())),
        )
        for b in brutas
    )
