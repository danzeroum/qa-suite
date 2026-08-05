#!/usr/bin/env python3
"""Afere que o smoke de GUI EXERCITOU os checks — a lição do D6.

Sem Chromium, os checks de `gui` pulam com instrução, o pytest sai 0, e o job
fica verde sem ter exercido nada. Verde por ausência é a pior forma de verde:
ele parece cobertura e é o contrário dela.

Foi exatamente isso que aconteceu com o `quality-gate` antes da correção do D6 —
os quatro testes do contrato do alvo fixture PULAVAM sem navegador e o job
aprovava sem conferir o R7 que ele existe para cobrir. Este script transforma
"não rodou" em vermelho.

Script, e não trecho embutido no YAML, por dois motivos: um heredoc dentro de um
bloco de workflow é frágil e ilegível, e — mais importante — assim a própria
guarda ganha teste (`tests/test_afere_smoke_gui.py`). Guarda sem teste é a
classe de defeito "a garantia existe, a ligação não".

Somente stdlib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIMENSAO = "gui"


def aferir(laudo: dict) -> str:
    """Devolve o motivo da reprovação, ou "" quando o smoke exercitou de verdade.

    Função pura: recebe o laudo já lido. É o que permite testá-la sobre dados
    fabricados, inclusive os casos que não dá para produzir num CI de verdade.
    """
    dimensao = (laudo.get("by_dimension") or {}).get(DIMENSAO) or {}
    if not dimensao:
        return (f"o laudo não tem a dimensão `{DIMENSAO}` — nenhum check de GUI foi "
                "coletado (marcador ausente? seleção errada?)")
    if dimensao.get("failed"):
        return (f"{dimensao['failed']} check(s) de GUI REPROVARAM a página conforme: "
                "é falso positivo, e falso positivo em acessibilidade custa a "
                "credibilidade da bateria inteira")
    if not dimensao.get("passed"):
        return (f"nenhum check de GUI passou — todos pularam ({dimensao}). "
                "Chromium ausente? Verde por ausência não é verde")
    return ""


def main(argv: list[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    caminho = Path(argumentos[0] if argumentos else "report/smoke-gui/summary.json")
    if not caminho.exists():
        print(f"::error::smoke de GUI não gerou {caminho}", file=sys.stderr)
        return 1
    try:
        laudo = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        print(f"::error::laudo do smoke ilegível ({erro})", file=sys.stderr)
        return 1

    motivo = aferir(laudo)
    if motivo:
        print(f"::error::{motivo}", file=sys.stderr)
        return 1
    print(f"smoke de GUI exercitado: {laudo['by_dimension'][DIMENSAO]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
