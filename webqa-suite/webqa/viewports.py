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


def com_zoom(viewport: Viewport, percentual: int) -> Viewport:
    """O mesmo perfil sob N% de ampliação, emulada por viewport lógico menor.

    200% de zoom é, para efeito de layout, uma viewport com metade da largura e
    da altura: o conteúdo ocupa o dobro do espaço relativo. É a forma de emular
    ampliação que funciona igual nas três engines — o Playwright não expõe o
    atalho de zoom do navegador de maneira estável entre elas.

    O nome carrega o percentual (`desktop@200%`) porque ele aparece na mensagem
    do assert, e "desktop" duas vezes com números diferentes confunde quem lê.
    """
    if percentual <= 0:
        raise ValueError(f"percentual de zoom precisa ser positivo: {percentual!r}")
    fator = 100 / percentual
    return Viewport(
        nome=f"{viewport.nome}@{percentual}%",
        largura=max(1, round(viewport.largura * fator)),
        altura=max(1, round(viewport.altura * fator)),
        mobile=viewport.mobile,
        toque=viewport.toque,
    )


# Engines que recusam `is_mobile`. Lista, e não um `if engine == "firefox"`
# espalhado: quando o Firefox implementar (ou outra engine deixar de aceitar),
# muda-se aqui e a decisão continua num lugar só.
ENGINES_SEM_EMULACAO_MOVEL = ("firefox",)


def sem_emulacao_movel(engine: str | None) -> bool:
    """A engine recusa emulação móvel?"""
    return (engine or "").strip().lower() in ENGINES_SEM_EMULACAO_MOVEL


def nota_de_emulacao(engine: str | None, viewport: Viewport | None) -> str:
    """A frase que acompanha o laudo quando a emulação foi omitida.

    Existe porque a diferença precisa aparecer NO LAUDO, não só no código: um
    resultado de "perfil móvel" que na verdade mediu largura sem emulação, e não
    diz isso, mente por omissão sobre o que foi exercido.
    """
    if not (sem_emulacao_movel(engine) and viewport is not None and viewport.mobile):
        return ""
    return (f"Nota: em {engine} o perfil `{viewport.nome}` roda como LARGURA "
            f"({viewport.largura}px) SEM emulação móvel — a engine recusa `is_mobile`. "
            "Veredito de largura vale; comportamento de toque NÃO foi exercido.")


def opcoes_de_contexto(viewport: Viewport | None = None, *, engine: str | None = None,
                       **extra) -> dict:
    """Kwargs de `browser.new_context(...)` para um viewport, mais o que vier.

    Função PURA: nenhum navegador, nenhum I/O. É o que torna possível provar o
    isolamento sem subir Chromium — e o que mantém o `conftest.py` como casca
    fina sobre a biblioteca.

    `is_mobile`/`has_touch` só entram quando são verdadeiros, porque **o Firefox
    recusa `is_mobile`** e mandá-lo sempre faria todo perfil de desktop quebrar
    naquela engine por um campo que ele nem usa.

    **A pendência da OS-41, decidida na OS-48 e escrita aqui.** O perfil móvel em
    Firefox roda como LARGURA SEM EMULAÇÃO: `is_mobile` e `has_touch` são
    omitidos, o contexto abre, e a nota de `nota_de_emulacao` acompanha o laudo.

    A alternativa — pular o perfil móvel no Firefox — foi recusada com motivo:
    ela apagaria da matriz de compatibilidade exatamente a combinação
    "engine alternativa × tela estreita", que é onde a incompatibilidade de
    layout mais aparece. Perder o veredito de largura em três dos cinco perfis
    para não perder o de toque em nenhum é trocar o achado provável pelo raro.

    O limite é real e por isso vai escrito no laudo: naquela engine o perfil
    móvel mede largura, não toque. Check cujo veredito dependa da EMULAÇÃO — e
    não da largura — deve pular pontualmente, com motivo; nenhum dos checks de
    hoje é o caso, porque todos julgam por largura.
    """
    opcoes: dict = {}
    if viewport is not None:
        opcoes["viewport"] = {"width": viewport.largura, "height": viewport.altura}
        if viewport.mobile and not sem_emulacao_movel(engine):
            opcoes["is_mobile"] = True
        if viewport.toque and not sem_emulacao_movel(engine):
            opcoes["has_touch"] = True
    opcoes.update(extra)
    return opcoes
