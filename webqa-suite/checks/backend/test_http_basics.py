"""Disponibilidade e correção básica do protocolo (nível: integração).

Atributos de qualidade cobertos: disponibilidade e confiabilidade.
Foco em limites e riscos: erro 404 tratado, redirecionamento a HTTPS.
"""
import pytest

pytestmark = pytest.mark.backend


def test_home_responde_2xx(home_response):
    assert 200 <= home_response.status_code < 300, (
        f"Página inicial retornou {home_response.status_code}"
    )


def test_https_e_usado(home_response):
    assert home_response.url.scheme == "https", (
        "Tráfego final não está sobre HTTPS — risco de segurança e LGPD "
        "(dados pessoais em trânsito sem criptografia)."
    )


def test_http_redireciona_para_https(client, settings):
    if not settings.target_url.startswith("https://"):
        pytest.skip("Alvo já configurado sem HTTPS.")
    insecure = settings.target_url.replace("https://", "http://", 1)
    resp = client.get(insecure)
    assert resp.url.scheme == "https", (
        "Acesso via http:// não redireciona para https://."
    )


def test_404_tratado_sem_vazamento(client, settings):
    """Erro deve ser controlado: status 404 e SEM stack trace exposto
    (Segurança por Design: nunca vazar detalhes internos)."""
    resp = client.get(settings.target_url + "/webqa-rota-inexistente-9f3a")
    assert resp.status_code in (404, 410), f"Rota inexistente retornou {resp.status_code}"
    body = resp.text.lower()
    for leak in ("traceback", "stacktrace", "exception in", "ora-", "sqlstate", "fatal error"):
        assert leak not in body, f"Página de erro vaza detalhe interno: '{leak}'"


def test_metodo_nao_suportado_controlado(client, settings):
    resp = client.request("TRACE", settings.target_url)
    assert resp.status_code in (403, 404, 405, 501), (
        f"TRACE deveria ser rejeitado de forma controlada, retornou {resp.status_code}"
    )
