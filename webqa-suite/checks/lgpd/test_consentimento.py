"""Consentimento prévio: nada de rastreamento ANTES da manifestação do titular.

LGPD Art. 7º I e 8º §4 — consentimento é prévio, livre, informado e específico;
finalidades genéricas não valem. Cookie de analytics gravado no primeiro load,
antes de qualquer clique no banner, é tratamento sem base legal declarada.

Método: 100% PASSIVO. A suíte carrega a página e observa. Não clica em
"aceitar", não clica em "recusar" — interagir com o banner de um terceiro é
sondagem ativa (gate WEBQA_ACTIVE_PROBES_AUTHORIZED, Fase 2).
"""
import pytest

from webqa.trackers import host_of, is_tracker

pytestmark = [pytest.mark.lgpd, pytest.mark.browser]

# Cookies cuja finalidade é notoriamente analytics/ads (nome é assinatura).
_COOKIES_NAO_ESSENCIAIS = frozenset({"_ga", "_gid", "_gat", "_fbp", "_fbc", "_ttp"})
# Famílias com sufixo variável: _ga_G-XXXX (GA4), _hjSession*, _clck/_clsk.
_PREFIXOS_NAO_ESSENCIAIS = ("_ga_", "_gat_", "_hj", "_cl")

# Acima disto, o primeiro load parece estar montando perfil sem consentimento —
# mas o nome não prova finalidade, então informa em vez de reprovar.
_MAX_COOKIES_DESCONHECIDOS = 5


def _nao_essencial(nome: str) -> bool:
    return nome in _COOKIES_NAO_ESSENCIAIS or nome.startswith(_PREFIXOS_NAO_ESSENCIAIS)


def test_sem_trackers_antes_do_consentimento(network_log, settings):
    """Nenhuma requisição a rastreador conhecido durante o primeiro load."""
    allowlist = settings.lgpd_allowed_third_parties
    ofensores = sorted({host_of(r.url) for r in network_log.requests if is_tracker(r.url, allowlist)})
    assert not ofensores, (
        f"{len(ofensores)} rastreador(es) dispararam ANTES de qualquer consentimento "
        f"(LGPD Art. 7º I e 8º §4): {ofensores[:10]}"
        + (" …" if len(ofensores) > 10 else "")
        + "\nCorreção: carregar tags só APÓS o aceite. Terceiro autorizado pelo "
        "controlador vai em lgpd.allowed_third_parties (config.yaml)."
    )


def test_sem_cookies_nao_essenciais_pre_aceite(network_log):
    """Cookies de analytics/ads gravados sem interação com o banner."""
    nomes = network_log.cookie_names()
    if not nomes:
        return  # nenhum cookie no primeiro load é o melhor resultado possível

    ofensores = sorted({n for n in nomes if _nao_essencial(n)})
    assert not ofensores, (
        "Cookies de analytics/ads gravados antes de qualquer aceite "
        f"(LGPD Art. 7º I): {ofensores}. Somente cookies estritamente "
        "necessários podem preceder o consentimento."
    )

    desconhecidos = sorted({n for n in nomes if not _nao_essencial(n)})
    if len(desconhecidos) > _MAX_COOKIES_DESCONHECIDOS:
        pytest.xfail(
            f"{len(desconhecidos)} cookies de finalidade não identificável no primeiro "
            f"load (> {_MAX_COOKIES_DESCONHECIDOS}): {desconhecidos[:10]}. "
            "Sinal — não prova: o nome não revela a finalidade. Confronte com o "
            "inventário de cookies do controlador (Art. 9º)."
        )
