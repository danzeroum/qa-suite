"""VERIFICAÇÃO: sanitização de PII — casos de aceite dos Riscos 001/002."""
import pytest

from webqa.sanitize import safe_url, sanitize_text

pytestmark = pytest.mark.verification


# ---- Risco-001: sanitize_text ----

def test_mascara_email():
    assert sanitize_text("user joao@x.com falhou") == "user [EMAIL] falhou"


def test_mascara_token_e_cpf_em_url():
    out = sanitize_text("GET /a?token=abc123&cpf=529.982.247-25")
    assert "abc123" not in out and "529" not in out
    assert out == "GET /a?token=[TOKEN]&cpf=[CPF]"


def test_cpf_sem_pontuacao():
    assert sanitize_text("cpf do cliente: 52998224725") == "cpf do cliente: [CPF]"


def test_telefone_br():
    out = sanitize_text("contato (11) 91234-5678 retornou erro")
    assert "91234" not in out and "[FONE]" in out


def test_texto_sem_pii_passa_inalterado():
    t = "AssertionError: LCP 3100ms acima do orçamento de 2500ms"
    assert sanitize_text(t) == t


def test_vazio():
    assert sanitize_text("") == ""


def test_nao_engole_numeros_de_metricas():
    t = "p95=1500ms em 30 requisições"
    assert sanitize_text(t) == t


# ---- Risco-002: safe_url ----

def test_url_com_query_e_ocultada():
    assert safe_url("https://a.com/p?email=x@y.com&t=abc") == "https://a.com/p?[params ocultos]"


def test_url_sem_query_identica():
    assert safe_url("https://a.com/p") == "https://a.com/p"


def test_url_raiz():
    assert safe_url("https://a.com") == "https://a.com"
