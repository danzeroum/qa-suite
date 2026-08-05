#!/usr/bin/env python3
"""Afere que a matriz noturna de GUI FECHOU a conta — a lição do D6, de novo.

O slot noturno roda a dimensão `gui` contra as três engines e a matriz inteira de
viewports. O modo de falha que ele tem e o `ci.yml` não tem é a **engine que não
instalou**: os checks pulam, o pytest sai 0, e o artefato fica indistinguível
entre "as três engines concordaram" e "só uma rodou". Verde por ausência, com
mais superfície.

Este script transforma isso em vermelho. Ele confere duas coisas, e só duas:

* **nada some** — executados + pulados fecham com o total coletado. Um check que
  desaparece do laudo por erro de coleta não deixa marca em contagem nenhuma;
* **o skip é NOMEADO** — todo pulo traz motivo escrito. Skip anônimo é o que
  permite uma engine sumir da conta sem ninguém notar.

Não julga o alvo: o fixture é não conforme de propósito e reprovar é o esperado.
Julga a EXECUÇÃO.

Somente stdlib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIMENSAO = "gui"


def aferir(laudo: dict) -> str:
    """Motivo da reprovação, ou "" quando a matriz fechou. Função pura."""
    resultados = [r for r in (laudo.get("results") or [])
                  if DIMENSAO in (r.get("dimensions") or [r.get("dimension")])]
    if not resultados:
        return (f"o laudo não tem nenhum resultado da dimensão `{DIMENSAO}` — a matriz "
                "não rodou (marcador ausente? seleção errada?)")

    contagem = (laudo.get("by_dimension") or {}).get(DIMENSAO) or {}
    somado = sum(int(contagem.get(chave) or 0)
                 for chave in ("passed", "failed", "skipped", "error"))
    if somado != len(resultados):
        return (f"a conta não fecha: {len(resultados)} resultados de `{DIMENSAO}` no laudo "
                f"contra {somado} somados em by_dimension ({contagem}). Um check sumiu "
                "entre a execução e o consolidado")

    mudos = [r["test"] for r in resultados
             if r.get("outcome") == "skipped" and not (r.get("detail") or "").strip()]
    if mudos:
        return (f"{len(mudos)} check(s) pularam SEM motivo escrito: {mudos[:5]}. "
                "Skip anônimo é como uma engine some da conta sem ninguém notar")
    return ""


def resumo(laudo: dict) -> str:
    contagem = (laudo.get("by_dimension") or {}).get(DIMENSAO) or {}
    pulados = [r for r in (laudo.get("results") or []) if r.get("outcome") == "skipped"]
    linhas = [f"matriz de GUI: {contagem}"]
    linhas += [f"  pulado: {r['test']} — {(r.get('detail') or '')[:120]}" for r in pulados[:10]]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    caminho = Path(argumentos[0] if argumentos else "report/matriz-gui/summary.json")
    if not caminho.exists():
        print(f"::error::a matriz de GUI não gerou {caminho}", file=sys.stderr)
        return 1
    try:
        laudo = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        print(f"::error::laudo da matriz ilegível ({erro})", file=sys.stderr)
        return 1

    motivo = aferir(laudo)
    if motivo:
        print(f"::error::{motivo}", file=sys.stderr)
        return 1
    print(resumo(laudo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
