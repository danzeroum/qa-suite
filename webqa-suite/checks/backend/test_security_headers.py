"""Segurança por Design no transporte: cabeçalhos e cookies.

Cobre recomendações OWASP básicas (análise dinâmica complementar ao SAST):
HSTS, CSP, X-Content-Type-Options, frame protection, cookies endurecidos,
não exposição de versão de servidor. Relevante para LGPD/GDPR: dados
pessoais exigem transporte e sessão protegidos.
"""
import pytest

pytestmark = pytest.mark.backend


def test_hsts_presente(home_response):
    assert "strict-transport-security" in home_response.headers, (
        "Sem HSTS — navegadores podem ser rebaixados a HTTP (downgrade attack)."
    )


def test_x_content_type_options(home_response):
    assert home_response.headers.get("x-content-type-options", "").lower() == "nosniff", (
        "Sem X-Content-Type-Options: nosniff — risco de MIME sniffing."
    )


def test_protecao_contra_clickjacking(home_response):
    has_xfo = "x-frame-options" in home_response.headers
    csp = home_response.headers.get("content-security-policy", "")
    assert has_xfo or "frame-ancestors" in csp, (
        "Sem X-Frame-Options nem CSP frame-ancestors — risco de clickjacking."
    )


def test_content_security_policy_existe(home_response):
    assert "content-security-policy" in home_response.headers, (
        "Sem Content-Security-Policy — principal mitigação de XSS ausente."
    )


def test_cookies_endurecidos(home_response):
    """Privilégio mínimo aplicado a sessão: Secure + HttpOnly + SameSite."""
    problemas = []
    for cookie_header in home_response.headers.get_list("set-cookie"):
        low = cookie_header.lower()
        nome = cookie_header.split("=", 1)[0]
        if "secure" not in low:
            problemas.append(f"{nome}: sem Secure")
        if "httponly" not in low:
            problemas.append(f"{nome}: sem HttpOnly")
        if "samesite" not in low:
            problemas.append(f"{nome}: sem SameSite")
    assert not problemas, "Cookies frágeis: " + "; ".join(problemas)


def test_nao_expoe_versao_de_servidor(home_response):
    for header in ("server", "x-powered-by", "x-aspnet-version"):
        valor = home_response.headers.get(header, "")
        assert not any(ch.isdigit() for ch in valor), (
            f"Header '{header}: {valor}' expõe versão — facilita ataques direcionados."
        )
