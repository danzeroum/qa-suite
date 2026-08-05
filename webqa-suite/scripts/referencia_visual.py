#!/usr/bin/env python3
"""Regrava a linha de base visual do alvo FABRICADO, com manifesto de procedência.

`make referencia-visual`. Sobe o alvo fabricado numa porta efêmera, captura cada
variação declarada em `data/gui-perfis.yaml::visual` e grava PNG + manifesto
JUNTOS — não há caminho neste script que grave só um.

**Só o alvo fabricado.** Não há opção de apontar isto para um site real: a
referência versionada vive no Git, e captura de alvo real não é versionável por
causa do R19 (pixel não passa pela borda de sanitização). Referência de alvo real
vive fora da árvore, sob `WEBQA_GUI_BASELINE_DIR`, e é gravada pela execução, não
por aqui.

**Variação com `regravar: false` é PULADA, e é o que mantém o contrato vivo.** A
página deslocada existe para exercer a direção `failed` do diff; regravá-la faria
o defeito se autocorrigir no primeiro comando, e o check nunca mais reprovaria.

Somente stdlib + Playwright.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fixture_target.servir import AlvoFixture  # noqa: E402
from webqa.referencia_visual import carregar_paginas, gravar  # noqa: E402
from webqa.viewports import carregar_perfis, opcoes_de_contexto  # noqa: E402

MOTIVO_PADRAO = ("linha de base do alvo fabricado, regravada por "
                 "`make referencia-visual` contra a página sem texto do contrato visual")


def main(argv: list[str] | None = None) -> int:
    from playwright.sync_api import sync_playwright

    paginas = [p for p in carregar_paginas() if p.regravar]
    pulados = [p.caminho for p in carregar_paginas() if not p.regravar]
    if not paginas:
        print("Nenhuma variação com `regravar: true` em data/gui-perfis.yaml::visual.")
        return 1

    perfis = carregar_perfis()
    agora = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    with AlvoFixture() as alvo, sync_playwright() as playwright:
        navegador = playwright.chromium.launch()
        try:
            for visual in paginas:
                contexto = navegador.new_context(
                    **opcoes_de_contexto(perfis[visual.viewport], engine="chromium"))
                try:
                    pagina = contexto.new_page()
                    pagina.goto(alvo.url.rstrip("/") + visual.caminho,
                                wait_until="load", timeout=60_000)
                    _gravar_variacao(pagina, visual, agora)
                finally:
                    contexto.close()
        finally:
            navegador.close()

    for caminho in pulados:
        print(f"PULADA (regravar: false): {caminho} — a referência dela é "
              "deliberadamente defasada e regravá-la apagaria a única direção "
              "`failed` do contrato visual.")
    return 0


def _gravar_variacao(pagina, visual, agora: str) -> None:
    destino = gravar(visual.artefato(), pagina.screenshot(), engine="chromium",
                     gravado_em=agora, motivo=MOTIVO_PADRAO)
    print(f"gravado: {destino}")
    for componente in visual.componentes:
        alvo = gravar(visual.artefato(componente),
                      pagina.locator(componente).screenshot(), engine="chromium",
                      gravado_em=agora,
                      motivo=f"{MOTIVO_PADRAO} — recorte do componente {componente}")
        print(f"gravado: {alvo}")


if __name__ == "__main__":
    raise SystemExit(main())
