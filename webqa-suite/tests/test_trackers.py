"""VERIFICAÇÃO: detecção de rastreadores e contrato do NetworkLog.

Unidade pura — nenhum alvo externo é tocado. O que se verifica aqui é a
CLASSIFICAÇÃO; se ela erra, toda a dimensão lgpd erra junto.
"""
import pytest

from webqa.trackers import LoggedRequest, NetworkLog, host_matches, host_of, is_tracker

pytestmark = pytest.mark.verification


# ---- Aceite de OS-01 ----

def test_subdominio_de_tracker_e_detectado():
    assert is_tracker("https://region1.google-analytics.com/g/collect", []) is True


def test_asset_do_alvo_nao_e_tracker():
    assert is_tracker("https://cdn.alvo.com/app.js", []) is False


def test_allowlist_vence_tracker():
    url = "https://region1.google-analytics.com/g/collect"
    assert is_tracker(url, ["google-analytics.com"]) is False
    assert is_tracker(url, ["region1.google-analytics.com"]) is False


# ---- Bordas de classificação ----

def test_dominio_exato_e_tracker():
    assert is_tracker("https://hotjar.com/x.js")
    assert is_tracker("http://static.hotjar.com/c/hotjar-1.js")


def test_substring_nao_basta():
    """Casamento é por rótulo de domínio, não por substring."""
    assert is_tracker("https://meugoogle-analytics.com.br/a.js") is False
    assert is_tracker("https://naosegment.com/a.js") is False


def test_esquema_nao_http_nao_e_tracker():
    for url in ("data:text/js,1", "blob:https://a.com/1", "about:blank"):
        assert is_tracker(url) is False
        assert host_of(url) == ""


def test_allowlist_com_www_e_espacos():
    assert is_tracker("https://hotjar.com/x.js", [" www.hotjar.com "]) is False


def test_allowlist_de_outro_host_nao_libera():
    assert is_tracker("https://hotjar.com/x.js", ["clarity.ms"]) is True


def test_host_matches_ignora_ponto_final_e_caixa():
    assert host_matches(host_of("https://WWW.Hotjar.COM./x"), "hotjar.com")


# ---- Contrato consumido por checks/lgpd ----

def _log():
    return NetworkLog(
        url="https://alvo.com",
        requests=(
            LoggedRequest("https://alvo.com/", "document"),
            LoggedRequest("https://cdn.alvo.com/app.js", "script"),
            LoggedRequest("https://www.googletagmanager.com/gtm.js?id=X", "script"),
            LoggedRequest("https://region1.google-analytics.com/g/collect", "xhr"),
            LoggedRequest("data:image/png;base64,AAA", "image"),
        ),
        cookies=({"name": "sessionid", "value": "x"}, {"name": "_ga", "value": "y"}),
    )


def test_hosts_ignora_urls_sem_host_e_nao_repete():
    assert _log().hosts() == [
        "alvo.com", "cdn.alvo.com", "www.googletagmanager.com", "region1.google-analytics.com",
    ]


def test_tracker_hosts_ordenado_e_unico():
    assert _log().tracker_hosts() == ["region1.google-analytics.com", "www.googletagmanager.com"]


def test_tracker_hosts_respeita_allowlist():
    assert _log().tracker_hosts(["googletagmanager.com"]) == ["region1.google-analytics.com"]


def test_cookie_names():
    assert _log().cookie_names() == ["sessionid", "_ga"]
