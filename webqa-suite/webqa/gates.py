"""Guardas técnicas de autorização — o que a suíte pode fazer CONTRA um alvo.

Dois gates independentes, porque são intrusões de natureza diferente:

* `WEBQA_LOAD_AUTHORIZED=1`  — gerar carga (risco de disponibilidade do alvo).
* `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` — sondagem ATIVA: submeter formulário de
  terceiro, aceitar/recusar banner de consentimento, exercer direito de titular.
  Isso escreve no sistema do alvo e pode criar registro de titular — não é
  observação, é interação.

Na Fase 1 toda a bateria LGPD é PASSIVA (só carrega e observa), então o gate de
sondagem ativa é criado e documentado, mas nenhum teste o consome ainda. O gate
vem antes do primeiro teste ativo de propósito: guarda que nasce junto com a
funcionalidade costuma nascer frouxa.
"""
from __future__ import annotations

import os

LOAD_ENV = "WEBQA_LOAD_AUTHORIZED"
ACTIVE_PROBES_ENV = "WEBQA_ACTIVE_PROBES_AUTHORIZED"


def _enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def load_authorized() -> bool:
    """Dono do alvo autorizou geração de carga?"""
    return _enabled(LOAD_ENV)


def active_probes_authorized() -> bool:
    """Dono do alvo autorizou sondagem ativa (escrita/interação)?"""
    return _enabled(ACTIVE_PROBES_ENV)


def require_active_probes() -> None:
    """Aborta o teste corrente se a sondagem ativa não foi autorizada.

    Skip (não fail): ausência de autorização não é defeito do alvo.
    """
    import pytest

    if not active_probes_authorized():
        pytest.skip(
            f"Sondagem ativa exige opt-in explícito: exporte {ACTIVE_PROBES_ENV}=1 "
            "somente com autorização documentada do dono do alvo (submeter "
            "formulário ou interagir com banner escreve no sistema dele)."
        )
