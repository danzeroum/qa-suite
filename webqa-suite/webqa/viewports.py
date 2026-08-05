"""Matriz de viewports da dimensão `gui` (OS-41).

Mesma doutrina de `webqa/navegador.py`, e pelo mesmo motivo: a lista de
viewports a exercitar é decisão da **execução** — `mobile,desktop` no PR para
não multiplicar o tempo de CI, matriz completa no noturno — e não propriedade do
alvo. Por isso vem de `WEBQA_VIEWPORTS`, e não do `Settings`.

**Fail-closed.** Nome desconhecido é ERRO, nunca filtro silencioso. Um typo
(`mobil`) no noturno não pode degenerar em "rodou zero viewports e passou" — é a
pior forma de verde falso, a que a suíte inteira existe para evitar.

Os perfis em si vivem em `data/gui-perfis.yaml`: são mapas, e o bloco
`thresholds` do `config.yaml` só carrega número (`webqa/config.py` faz `float()`
em toda chave). A partição é do código, não de gosto.

`opcoes_de_contexto` fica aqui, e não no `conftest.py`, pela lei da casa: o
detalhe vive em `webqa/`, os checks só conhecem fixtures (`docs/ARQUITETURA.md`).
Como função pura, ela é testável sem navegador — e é o que permite provar o
isolamento de contexto sem subir Chromium.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PERFIS_PADRAO = RAIZ / "data" / "gui-perfis.yaml"

ENV_VIEWPORTS = "WEBQA_VIEWPORTS"
# Os dois extremos que mais quebram. Cobrir os quatro no PR dobraria o tempo do
# job que roda em todo push, e o noturno existe para a matriz completa.
VIEWPORTS_PADRAO = ("mobile", "desktop")


@dataclass(frozen=True)
class Viewport:
    """Um perfil de viewport nomeado. Congelado: é snapshot de configuração."""

    nome: str
    largura: int
    altura: int
    mobile: bool = False
    toque: bool = False


def carregar_perfis(caminho: str | Path | None = None) -> dict[str, Viewport]:
    """Lê `data/gui-perfis.yaml` → {nome: Viewport}, na ordem declarada.

    Perfil sem `width`/`height` é erro de configuração e aborta aqui, não na
    primeira vez que alguém abrir um contexto: configuração pela metade tem de
    falhar onde a mensagem ainda sabe dizer qual chave falta.
    """
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    perfis: dict[str, Viewport] = {}
    for nome, bruto in (dados.get("viewports") or {}).items():
        if not isinstance(bruto, Mapping) or "width" not in bruto or "height" not in bruto:
            raise ValueError(
                f"perfil de viewport {nome!r} sem 'width'/'height' em gui-perfis.yaml")
        perfis[str(nome)] = Viewport(
            nome=str(nome),
            largura=int(bruto["width"]),
            altura=int(bruto["height"]),
            mobile=bool(bruto.get("mobile", False)),
            toque=bool(bruto.get("touch", False)),
        )
    if not perfis:
        raise ValueError("gui-perfis.yaml não declara nenhum viewport")
    return perfis


def viewports_configurados(env: Mapping[str, str] | None = None,
                           perfis: Mapping[str, Viewport] | None = None) -> tuple[Viewport, ...]:
    """Viewports a exercitar, lidos de `WEBQA_VIEWPORTS` (lista por vírgula).

    Ordem de declaração e unicidade preservadas — repetir um nome não roda duas
    vezes, e a ordem escrita é a ordem executada, para o laudo sair legível.
    """
    disponiveis = dict(perfis) if perfis is not None else carregar_perfis()
    origem = env if env is not None else os.environ
    bruto = origem.get(ENV_VIEWPORTS, "").strip()
    nomes = [n.strip().lower() for n in bruto.split(",")] if bruto else list(VIEWPORTS_PADRAO)

    escolhidos: dict[str, None] = {}
    for nome in nomes:
        if not nome:
            continue
        if nome not in disponiveis:
            raise ValueError(
                f"viewport desconhecido em {ENV_VIEWPORTS}: {nome!r}. "
                f"Válidos: {', '.join(disponiveis)}.")
        escolhidos.setdefault(nome, None)
    if not escolhidos:
        # Só alcançável com um valor todo feito de vírgulas e espaços. Cair para
        # o default seria transformar configuração sem sentido em execução
        # silenciosa — a mesma classe de erro que o fail-closed acima recusa.
        raise ValueError(f"{ENV_VIEWPORTS} definido mas sem nenhum viewport: {bruto!r}")
    return tuple(disponiveis[nome] for nome in escolhidos)


def opcoes_de_contexto(viewport: Viewport | None = None, **extra) -> dict:
    """Kwargs de `browser.new_context(...)` para um viewport, mais o que vier.

    Função PURA: nenhum navegador, nenhum I/O. É o que torna possível provar o
    isolamento sem subir Chromium — e o que mantém o `conftest.py` como casca
    fina sobre a biblioteca.

    `is_mobile`/`has_touch` só entram quando são verdadeiros. Não é economia de
    bytes: **o Firefox recusa `is_mobile`**, e mandá-lo sempre faria todo perfil
    de desktop quebrar naquela engine por um campo que ele nem usa. O perfil
    móvel EM Firefox segue sendo um problema em aberto — quem ligar a matriz
    completa (OS-48) decide entre skip honesto e viewport sem emulação, e essa
    decisão precisa ser tomada por escrito, não herdada daqui em silêncio.
    """
    opcoes: dict = {}
    if viewport is not None:
        opcoes["viewport"] = {"width": viewport.largura, "height": viewport.altura}
        if viewport.mobile:
            opcoes["is_mobile"] = True
        if viewport.toque:
            opcoes["has_touch"] = True
    opcoes.update(extra)
    return opcoes
