"""Seleção de engine de navegador para a dimensão browser (compatibilidade, C3).

Playwright traz três engines — chromium, firefox, webkit. A suíte mede o alvo em
todas as que o operador pedir, com skip HONESTO quando o binário de uma engine
não está instalado: engine ausente vira "pulado com instrução", nunca aprovação
silenciosa (a mesma regra do fixture `browser` no conftest).

Por que env e não `config.yaml`: a lista de engines é decisão da EXECUÇÃO —
`chromium` no PR para não triplicar o CI, matriz completa no noturno — e não
propriedade do alvo. Fica fora do `Settings` de propósito.

Somente stdlib.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

ENGINE_PADRAO = "chromium"
ENGINES_VALIDAS = ("chromium", "firefox", "webkit")
ENV_ENGINES = "WEBQA_BROWSER_ENGINES"


def engines_configurados(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Engines a exercitar, lidas de `WEBQA_BROWSER_ENGINES` (lista por vírgula).

    Default: só `chromium` — o PR não triplica o tempo de CI (R-Q5). O noturno
    declara a matriz completa. Ordem de declaração e unicidade preservadas.

    **Fail-closed**: engine desconhecida é ERRO, não filtro silencioso. Um typo
    (`chromiun`) no noturno não pode degenerar em "rodou zero engines e passou" —
    seria a pior forma de verde falso, a que a suíte inteira existe para evitar.
    """
    origem = env if env is not None else os.environ
    bruto = origem.get(ENV_ENGINES, "").strip()
    if not bruto:
        return (ENGINE_PADRAO,)
    escolhidas: dict[str, None] = {}
    for item in bruto.split(","):
        engine = item.strip().lower()
        if not engine:
            continue
        if engine not in ENGINES_VALIDAS:
            raise ValueError(
                f"engine de navegador desconhecida em {ENV_ENGINES}: {engine!r}. "
                f"Válidas: {', '.join(ENGINES_VALIDAS)}.")
        escolhidas.setdefault(engine, None)
    return tuple(escolhidas) or (ENGINE_PADRAO,)
