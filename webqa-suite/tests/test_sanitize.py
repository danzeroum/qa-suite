"""VERIFICAÇÃO: sanitização de PII — casos de aceite dos Riscos 001/002."""
import pytest

from webqa.sanitize import (
    encontrar_segredos,
    esquecer_valores_sensiveis,
    mascarar_valores_registrados,
    registrar_valor_sensivel,
    safe_url,
    sanitize_text,
)

pytestmark = pytest.mark.verification


@pytest.fixture(autouse=True)
def registro_limpo():
    """O registro por valor é de processo: um caso não pode herdar do outro,
    nem do ambiente da máquina de quem roda."""
    esquecer_valores_sensiveis()
    yield
    esquecer_valores_sensiveis()


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


# ---- OS-37: mascaramento por VALOR (senha de Basic Auth) ----

SENHA = "Xk7-senha-de-teste"


def test_valor_registrado_e_mascarado_em_qualquer_posicao():
    registrar_valor_sensivel(SENHA, "SENHA")
    assert SENHA not in sanitize_text(f"GET falhou: 401 para {SENHA} no header")
    assert "[SENHA]" in sanitize_text(f"usou {SENHA}")


def test_conjunto_vazio_nao_altera_texto():
    """Sem credencial registrada, a sanitização tem de continuar byte-idêntica."""
    t = "AssertionError: LCP 3100ms acima do orçamento de 2500ms"
    assert sanitize_text(t) == t
    assert mascarar_valores_registrados(t) == t


def test_valor_registrado_e_mascarado_antes_de_email_e_cpf():
    """Trava a ORDEM dentro de sanitize_text.

    Uma senha que CONTÉM um e-mail seria fatiada por `_EMAIL` se a passagem por
    valor não viesse primeiro — e o pedaço restante sairia publicado. Metade de
    um segredo é o segredo inteiro para quem tem a outra metade.
    """
    senha = "x9@corp.com7Kq"
    registrar_valor_sensivel(senha, "SENHA")
    saida = sanitize_text(f"falhou com {senha}")
    assert "7Kq" not in saida
    assert saida == "falhou com [SENHA]"


def test_valor_mais_longo_vence_o_mais_curto():
    """Começar pelo curto deixaria `joao:[SENHA]` — que entrega o usuário."""
    registrar_valor_sensivel(SENHA, "SENHA")
    registrar_valor_sensivel(f"joao:{SENHA}", "SENHA")
    assert mascarar_valores_registrados(f"userinfo joao:{SENHA} aqui") == "userinfo [SENHA] aqui"


def test_registro_ignora_valor_vazio():
    registrar_valor_sensivel("", "SENHA")
    assert mascarar_valores_registrados("qualquer coisa") == "qualquer coisa"


def test_valor_com_metacaractere_de_regex_e_tratado_literalmente():
    """Senha boa costuma ter `.`, `*`, `(` — compilar como padrão seria erro ou
    casamento errado."""
    senha = "a.*(b)+[c]"
    registrar_valor_sensivel(senha, "SENHA")
    assert mascarar_valores_registrados(f"x {senha} y") == "x [SENHA] y"
    assert mascarar_valores_registrados("aXXXb") == "aXXXb"


# ---- OS-37: cabeçalho Authorization (a forma com dois-pontos) ----

def test_mascara_authorization_com_dois_pontos():
    saida = sanitize_text("Authorization: Basic am9hbzpzM25oNA==")
    assert "am9hbzpzM25oNA" not in saida
    assert saida == "Authorization: [AUTHORIZATION]"


def test_mascara_authorization_de_qualquer_esquema():
    assert "abc.def" not in sanitize_text("authorization: Bearer abc.def")


def test_mascaramento_de_authorization_e_idempotente():
    """Sem o `(?!\\[)`, a segunda passada comeria o próprio placeholder."""
    uma = sanitize_text("Authorization: Basic am9hbzpzM25oNA==")
    assert sanitize_text(uma) == uma


def test_authorization_nao_vira_achado_de_seguranca():
    """Fica FORA de `_SEGREDOS` de propósito: prosa do alvo dizendo
    'Authorization: required' não é credencial exposta, e acusá-la em massa
    custaria a credibilidade da bateria inteira."""
    assert encontrar_segredos("Authorization: Basic am9hbzpzM25oNA==") == []


# ---- OS-37: safe_url e a credencial embutida ----

def test_safe_url_remove_credencial_embutida_sem_query():
    """O caminho 'sem query' devolvia a URL VERBATIM — o defeito que mais
    importava, porque `WEBQA_TARGET_URL` raramente tem query."""
    saida = safe_url("https://joao:s3nh4@a.com/p")
    assert "s3nh4" not in saida and "joao" not in saida
    assert saida == "https://[credencial oculta]@a.com/p"


def test_safe_url_remove_credencial_embutida_com_query():
    saida = safe_url("https://joao:s3nh4@a.com/p?x=1")
    assert "s3nh4" not in saida
    assert saida == "https://[credencial oculta]@a.com/p?[params ocultos]"


def test_safe_url_preserva_porta_e_ipv6():
    assert safe_url("http://[::1]:8130/x") == "http://[::1]:8130/x"
