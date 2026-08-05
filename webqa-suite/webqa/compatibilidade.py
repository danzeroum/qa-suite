"""Comparação entre engines — o que diverge entre chromium, firefox e webkit.

A matriz de engines já existe (`webqa/navegador.py`, `.github/workflows/
compatibilidade.yml`), e até aqui ela provava uma coisa só: que a dimensão
`browser` RODA nas três. Rodar nas três não é ser compatível nas três — um
layout pode montar em todas e ficar quebrado em uma.

**Por que só marcos DECLARADOS, e não todo elemento.** Antialiasing de fonte,
arredondamento de sub-pixel e métricas de fonte diferem por engine: comparar
todas as caixas produziria dezenas de divergências de 1px que não são defeito
nenhum, e o sinal verdadeiro — o cabeçalho que só no WebKit cobre o conteúdo —
morreria no ruído. A lista de marcos vive em `data/gui-perfis.yaml` porque é
decisão de quem conhece o alvo, não da biblioteca.

**Duas engines é o mínimo.** Comparar uma engine consigo mesma é sempre verde, e
esse verde seria indistinguível do verde legítimo — a regra 9 de `docs/GUI.md
§2.2` outra vez. Com menos de duas o check PULA, e o motivo diz quantas havia.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from webqa.geometria import Caixa
from webqa.viewports import PERFIS_PADRAO

# Abaixo disto não há o que comparar. Não é preferência: é a diferença entre
# medir compatibilidade e afirmar compatibilidade a partir de uma amostra só.
MINIMO_DE_ENGINES = 2

# Só geometria HORIZONTAL, e a exclusão do eixo vertical foi medida, não suposta.
#
# `y` e `altura` acumulam: cada diferença de métrica de fonte e de entrelinha da
# página inteira soma dentro deles. Na matriz local desta OS, o `body` do alvo
# fabricado mediu 1776px no Chromium e 1797px no Firefox — 21px de diferença sem
# nada estar quebrado, só texto renderizado por duas engines. Um limiar que
# absorvesse isso (>21px) já não pegaria defeito nenhum.
#
# `x` e `largura` vêm do modelo de caixa, não do texto, e são onde a quebra entre
# engines de fato aparece: flex/grid interpretado diferente, extravasamento,
# elemento que não cabe. É o eixo que dá sinal.
#
# O que se perde: um colapso VERTICAL exclusivo de uma engine. Ele não fica sem
# dono — quando o elemento some, `ausentes_de` o pega; quando ele salta, o CLS
# por viewport pega; quando extravasa, GUI-RESP-01 pega.
CAMPOS_COMPARADOS = ("x", "largura")


@dataclass(frozen=True)
class Divergencia:
    """Um marco cuja caixa diverge entre engines além da tolerância."""

    marco: str
    campo: str                  # x | y | largura | altura
    valores: tuple[tuple[str, float], ...]
    desvio: float

    def __str__(self) -> str:
        medidas = ", ".join(f"{engine}={valor:.0f}px" for engine, valor in self.valores)
        return f"{self.marco} · {self.campo}: {medidas} (desvio {self.desvio:.0f}px)"


def pode_comparar(engines) -> bool:
    """Há material para comparação? Menos de duas engines é ausência de medida."""
    return len(set(engines)) >= MINIMO_DE_ENGINES


def motivo_de_pular(engines) -> str:
    presentes = sorted(set(engines))
    return (f"Comparação entre engines exige pelo menos {MINIMO_DE_ENGINES}; "
            f"{len(presentes)} disponível(is): {presentes or 'nenhuma'}. "
            "Instale as demais com `python -m playwright install firefox webkit` "
            "(a matriz completa roda no noturno). Uma engine só não comprova "
            "compatibilidade: comparar uma engine consigo mesma é sempre verde.")


def divergencias(por_engine: Mapping[str, Mapping[str, Caixa]], *,
                 tolerancia_px: float) -> tuple[Divergencia, ...]:
    """Marcos cujas caixas se afastam além da tolerância entre as engines.

    Compara o EXTREMO — maior menos menor —, e não pares: com três engines, dois
    pares dentro da tolerância podem somar um desvio que estoura, e é o desvio
    total que a pessoa vê na tela.

    Marco ausente em alguma engine NÃO vira divergência de posição: ausência é
    outro achado, com outra causa e outra correção, e misturá-lo aqui daria um
    número de pixels para um elemento que não existe (`ausentes_de`).
    """
    achados: list[Divergencia] = []
    engines = sorted(por_engine)
    for marco in sorted(_marcos_comuns(por_engine)):
        for campo in CAMPOS_COMPARADOS:
            valores = tuple((engine, float(getattr(por_engine[engine][marco], campo)))
                            for engine in engines)
            numeros = [valor for _, valor in valores]
            desvio = max(numeros) - min(numeros)
            if desvio > tolerancia_px:
                achados.append(Divergencia(marco, campo, valores, desvio))
    return tuple(sorted(achados, key=lambda d: -d.desvio))


def _marcos_comuns(por_engine: Mapping[str, Mapping[str, Caixa]]) -> set[str]:
    conjuntos = [set(caixas) for caixas in por_engine.values()]
    return set.intersection(*conjuntos) if conjuntos else set()


def ausentes_de(por_engine: Mapping[str, Mapping[str, Caixa]]) -> dict[str, tuple[str, ...]]:
    """{marco: engines em que ele NÃO apareceu}.

    Marco que some numa engine é o achado mais grave desta família, e o mais
    fácil de perder: ele não produz desvio de pixel nenhum, porque não há caixa
    para medir. Sem esta função a comparação diria "tudo dentro da tolerância"
    sobre uma página que perdeu a navegação inteira no WebKit.
    """
    engines = sorted(por_engine)
    todos = set().union(*(set(caixas) for caixas in por_engine.values())) if por_engine else set()
    faltas = {}
    for marco in sorted(todos):
        sem = tuple(engine for engine in engines if marco not in por_engine[engine])
        if sem:
            faltas[marco] = sem
    return faltas


def erros_exclusivos(por_engine: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    """{engine: erros que SÓ ela produziu}.

    Exclusivo, e não "quantos": erro que aparece nas três é defeito do alvo e já
    tem dono — `checks/frontend/test_rendering.py::test_console_sem_erros_js`.
    O que só esta família enxerga é o erro que UMA engine produz, porque aí a
    causa é a engine (ou um recurso que só ela não suporta), e o visitante que
    usa aquela engine é o único a sofrer.

    **Serve a dois baldes com pesos diferentes**, e a separação foi medida nesta
    OS. Exceção de JavaScript exclusiva é COMPORTAMENTO: o script da página
    lançou numa engine e não na outra. Erro de console exclusivo é, muitas vezes,
    apenas RELATO: na matriz local o Chromium registrou
    `net::ERR_NAME_NOT_RESOLVED` para o domínio `.invalid` do alvo fabricado e o
    Firefox não registrou nada — o recurso falhou nas duas, só uma resolveu
    contar. Comparar strings de console entre engines mede quem é mais verboso
    tanto quanto mede quem quebrou.

    Por isso o chamador reprova pelo primeiro balde e abranda pelo segundo.
    """
    engines = sorted(por_engine)
    conjuntos = {engine: set(por_engine[engine]) for engine in engines}
    exclusivos = {}
    for engine in engines:
        outras = set().union(*(conjuntos[o] for o in engines if o != engine)) if len(engines) > 1 else set()
        so_dela = tuple(sorted(conjuntos[engine] - outras))
        if so_dela:
            exclusivos[engine] = so_dela
    return exclusivos


def carregar_marcos(caminho: str | Path | None = None) -> tuple[str, ...]:
    """Seletores dos marcos comparados, de `data/gui-perfis.yaml`."""
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    bruto = (dados.get("compatibilidade") or {}).get("marcos") or []
    return tuple(str(seletor) for seletor in bruto)


# ---------- Coletor ----------

# Caixa de cada marco declarado. Devolve MAPA e não lista: o marco ausente
# simplesmente não aparece, e é `ausentes_de` que decide o que isso significa.
# Uma lista com buraco obrigaria a comparar por posição, e posição depende da
# ordem em que a engine devolveu — que é justamente o que não se pode assumir
# igual entre engines.
JS_MARCOS = """
(seletores) => {
  const saida = {};
  for (const seletor of seletores) {
    const el = document.querySelector(seletor);
    if (!el) { continue; }
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') { continue; }
    const r = el.getBoundingClientRect();
    if (r.width <= 0 && r.height <= 0) { continue; }
    saida[seletor] = {x: r.x, y: r.y, largura: r.width, altura: r.height};
  }
  return saida;
}
"""


def caixas_de(bruto: Mapping[str, Mapping[str, float]]) -> dict[str, Caixa]:
    """Traduz o que `JS_MARCOS` devolveu para o vocabulário da casa."""
    return {
        seletor: Caixa(seletor=seletor, x=float(valores.get("x") or 0.0),
                       y=float(valores.get("y") or 0.0),
                       largura=float(valores.get("largura") or 0.0),
                       altura=float(valores.get("altura") or 0.0))
        for seletor, valores in (bruto or {}).items()
    }
