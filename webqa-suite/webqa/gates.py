"""Guardas técnicas de autorização — o que a suíte pode fazer CONTRA um alvo.

Gates independentes, um por natureza de risco. Autorizar um NUNCA autoriza
outro: cada um é um consentimento distinto, e misturá-los é assumir permissão
que ninguém deu. Só a string exata `"1"` autoriza (fail-closed: `"true"`, `" 1"`
e afins não ligam por engano).

* `WEBQA_LOAD_AUTHORIZED=1` — gerar carga (risco de disponibilidade do alvo).
* `WEBQA_DISCOVERY_AUTHORIZED=1` — descoberta de conteúdo não linkado (Fase C1):
  perguntar ao servidor por recursos que ele não ofereceu, `HEAD`-first,
  **read-only, nunca escreve**. Existência já é o achado.
* `WEBQA_ACTIVE_PROBES_AUTHORIZED=1` — sondagem ATIVA de escrita (C2): submeter
  formulário de terceiro, aceitar/recusar banner de consentimento, exercer
  direito de titular. Escreve no sistema do alvo e pode criar registro de
  titular — não é observação, é interação. Descoberta (C1) e escrita (C2) são
  gates separados porque os riscos são separados: ler o que não foi linkado não
  é o mesmo que escrever.
* `WEBQA_ACTIVE_PROBES_KILL=1` — parada de emergência: interrompe o host
  corrente no laço da sondagem, independentemente dos gates acima.

Os gates de sondagem vêm antes do primeiro teste que os consome, de propósito:
guarda que nasce junto com a funcionalidade costuma nascer frouxa. Na Fase 1 a
bateria LGPD é PASSIVA e a Fase C está travada, então nenhum teste os consome
ainda.

O gate de LLM é de outra natureza e por isso separado dos de alvo:

* `WEBQA_LLM_ENABLED=1` — ligar a camada de sumário por LLM local (docs/LLM.md).
  Os outros autorizam agir CONTRA o alvo; este autoriza processar achados já
  produzidos. Juntá-los faria autorizar carga ligar IA — e cada mistura desse
  tipo é uma autorização que ninguém deu.

Escopo é ortogonal a todos: `require_escopo` pula um alvo fora da allowlist
mesmo com o gate aberto — autorização de técnica não é autorização de host.
"""
from __future__ import annotations

import os

LOAD_ENV = "WEBQA_LOAD_AUTHORIZED"
DISCOVERY_ENV = "WEBQA_DISCOVERY_AUTHORIZED"      # C1: descoberta read-only
ACTIVE_PROBES_ENV = "WEBQA_ACTIVE_PROBES_AUTHORIZED"  # C2: sondagem de escrita
KILL_ENV = "WEBQA_ACTIVE_PROBES_KILL"             # parada de emergência
LLM_ENV = "WEBQA_LLM_ENABLED"


def _enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def load_authorized() -> bool:
    """Dono do alvo autorizou geração de carga?"""
    return _enabled(LOAD_ENV)


def discovery_authorized() -> bool:
    """Dono do alvo autorizou descoberta de conteúdo não linkado (Fase C1)?

    Read-only: `HEAD`, nunca escreve. Autorizar descoberta NÃO autoriza escrita
    — para C2 use `ACTIVE_PROBES_ENV`. Gates independentes porque os riscos são
    independentes: ler o que não foi linkado não é escrever no sistema do alvo.
    """
    return _enabled(DISCOVERY_ENV)


def active_probes_authorized() -> bool:
    """Dono do alvo autorizou sondagem ativa (escrita/interação, Fase C2)?"""
    return _enabled(ACTIVE_PROBES_ENV)


def kill_switch_active() -> bool:
    """Parada de emergência ligada?

    Quando verdadeira, o laço da sondagem interrompe o host corrente,
    independentemente de qualquer gate de autorização. Fail-closed como os
    demais: só `"1"` a ativa.
    """
    return _enabled(KILL_ENV)


def llm_enabled() -> bool:
    """O operador ligou a camada de sumário por LLM local?

    Desligada por padrão (docs/LLM.md §2.5). Com o gate fechado nada é
    instanciado e nenhum endpoint é resolvido — a suíte roda sem IA a menos que
    alguém peça, e o laudo determinístico não muda de forma por causa disto.
    """
    return _enabled(LLM_ENV)


def require_discovery() -> None:
    """Aborta o teste corrente se a descoberta read-only (C1) não foi autorizada.

    Skip (não fail): ausência de autorização não é defeito do alvo.
    """
    import pytest

    if not discovery_authorized():
        pytest.skip(
            f"[gate:discovery] Descoberta read-only exige opt-in: exporte "
            f"{DISCOVERY_ENV}=1 com autorização documentada do dono do alvo."
        )


def require_escopo(escopo, url: str) -> None:
    """Aborta (skip, não fail) se a URL não está no escopo autorizado.

    Ortogonal aos gates: autorizar a técnica não autoriza o host. Recebe o
    `Escopo` por parâmetro (não importa `webqa.escopo`) e só depende de
    `esta_no_escopo(url) -> bool` — comparação de origem, não toca a rede.
    """
    import pytest

    if not escopo.esta_no_escopo(url):
        pytest.skip(
            f"[gate:escopo] {url} fora do escopo autorizado — adicione o host ao "
            "escopo com autorização documentada antes de sondá-lo."
        )


def require_active_probes() -> None:
    """Aborta o teste corrente se a sondagem ativa (escrita, C2) não foi autorizada.

    Skip (não fail): ausência de autorização não é defeito do alvo.
    """
    import pytest

    if not active_probes_authorized():
        pytest.skip(
            f"[gate:active_probes] Sondagem ativa exige opt-in explícito: exporte "
            f"{ACTIVE_PROBES_ENV}=1 somente com autorização documentada do dono do "
            "alvo (submeter formulário ou interagir com banner escreve no sistema dele)."
        )
