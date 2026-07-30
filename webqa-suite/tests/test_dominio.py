"""VERIFICAÇÃO dos value objects da dimensão `seguranca` (docs/SEGURANCA.md §3).

A invariante que este módulo existe para provar é ética, não técnica: **não há
como instanciar um `Finding` com segredo em claro**. Um teste que apenas
verificasse "o check lembrou de mascarar" mediria disciplina; aqui se mede
impossibilidade — tenta-se criar o objeto proibido e observa-se que ele nasce
mascarado.

O outro risco coberto é o inverso do óbvio: `ler_corpo` acima do teto devolve
`None`, e um consumidor que lesse isso como "nada encontrado" transformaria
limite de memória em atestado de segurança. Por isso `Corpo` carrega
`avaliavel`, e há teste de que o motivo chega junto.

Unidade pura: sem rede, sem navegador.
"""
from __future__ import annotations

import dataclasses

import pytest

from webqa.dominio import (
    TETO_CORPO_BYTES,
    Corpo,
    Finding,
    Recurso,
    ler_corpo,
    mesma_origem,
    texto_do_corpo,
)
from webqa.sanitize import encontrar_segredos, mascarar_segredos

pytestmark = pytest.mark.verification

AKIA = "AKIAIOSFODNN7EXAMPLE"
JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
       "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
GITHUB = "ghp_" + "a" * 36
STRIPE = "sk_live_" + "b" * 24
GOOGLE = "AIza" + "C" * 35


class _Resposta:
    """Dublê de resposta do Playwright: url, status, headers e body()."""

    def __init__(self, url, status=200, headers=None, corpo=b"", explode=False):
        self.url = url
        self.status = status
        self.headers = headers or {}
        self._corpo = corpo
        self._explode = explode
        self.leituras = 0

    def body(self) -> bytes:
        self.leituras += 1
        if self._explode:
            raise RuntimeError("corpo indisponível")
        return self._corpo


# ---------- A invariante ----------

def test_finding_nasce_com_a_evidencia_mascarada():
    """Aceite da OS: instanciar com segredo em claro é IMPOSSÍVEL."""
    achado = Finding(tipo="segredo_em_js", recurso="https://alvo.example/app.js",
                     severidade="alta", evidencia=f"const k = '{AKIA}'", fase="A")
    assert AKIA not in achado.evidencia
    assert "[AWS_ACCESS_KEY_ID]" in achado.evidencia
    assert not achado.contem_segredo_em_claro


@pytest.mark.parametrize("segredo,rotulo", [
    (AKIA, "AWS_ACCESS_KEY_ID"), (JWT, "JWT"), (PEM, "PEM_PRIVATE_KEY"),
    (GITHUB, "GITHUB_TOKEN"), (STRIPE, "STRIPE_SECRET_KEY"), (GOOGLE, "GOOGLE_API_KEY"),
])
def test_todo_formato_de_segredo_e_mascarado_no_construtor(segredo, rotulo):
    achado = Finding("segredo", "https://a/x.js", "alta", f"valor: {segredo}", "A")
    assert segredo not in achado.evidencia
    assert rotulo in achado.evidencia


def test_a_url_do_recurso_tambem_e_sanitizada():
    """Segredo em query string é segredo igual — e a URL vai para o relatório."""
    achado = Finding("segredo", f"https://a/cb?token={AKIA}", "alta", "x", "A")
    assert AKIA not in achado.recurso


def test_str_do_finding_nao_vaza_segredo():
    achado = Finding("segredo", "https://a/x.js", "alta", f"k={AKIA}", "A")
    assert AKIA not in str(achado)


def test_severidade_e_fase_invalidas_sao_recusadas():
    with pytest.raises(ValueError, match="severidade"):
        Finding("t", "r", "gravissima", "e", "A")
    with pytest.raises(ValueError, match="fase"):
        Finding("t", "r", "alta", "e", "Z")


def test_finding_e_imutavel():
    """Congelado: não dá para burlar a sanitização atribuindo depois."""
    achado = Finding("t", "r", "alta", "e", "A")
    with pytest.raises(dataclasses.FrozenInstanceError):
        achado.evidencia = AKIA


# ---------- Detector de segredos ----------

def test_hash_hex_nao_e_falso_positivo():
    """sha256 em hex não é credencial; entropia não é critério nesta suíte."""
    sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert encontrar_segredos(sha) == []
    assert mascarar_segredos(sha) == sha


def test_texto_limpo_passa_inalterado():
    limpo = "Nenhum segredo aqui, só prosa e um número 12345."
    assert mascarar_segredos(limpo) == limpo
    assert encontrar_segredos(limpo) == []


def test_credencial_nomeada_preserva_o_nome_do_campo():
    """Localizar o campo importa; republicar o valor, não."""
    mascarado = mascarar_segredos('{"api_key": "s3cr3t0-muito-longo-aqui"}')
    assert "api_key" in mascarado
    assert "s3cr3t0-muito-longo-aqui" not in mascarado


def test_severidade_do_pem_e_alta():
    assert ("PEM_PRIVATE_KEY", "alta") in encontrar_segredos(PEM)


# ---------- Origem: www e sem-www são o mesmo site ----------

@pytest.mark.parametrize("url,esperado", [
    ("https://alvo.example/app.js", True),
    ("https://www.alvo.example/app.js", True),
    ("http://alvo.example/x.png", True),
    ("https://cdn.terceiro.example/lib.js", False),
    ("https://cdn.alvo.example/lib.js", False),
])
def test_mesma_origem_normaliza_www_mas_nao_engole_subdominio(url, esperado):
    assert mesma_origem(url, "https://www.alvo.example/") is esperado


def test_recurso_de_terceiro_nao_e_de_origem():
    rec = Recurso.de_resposta(_Resposta("https://cdn.terceiro.example/a.js"),
                              "https://alvo.example/")
    assert rec.from_origin is False


# ---------- Recurso ----------

def test_recurso_mapeia_headers_em_minusculas_e_content_type_sem_charset():
    resposta = _Resposta("https://alvo.example/app.js", 200,
                         {"Content-Type": "application/javascript; charset=UTF-8",
                          "Content-Length": "1234", "X-Frame-Options": "DENY"})
    rec = Recurso.de_resposta(resposta, "https://alvo.example/")
    assert rec.content_type == "application/javascript"
    assert rec.cabecalho("x-frame-options") == "DENY"
    assert rec.headers["content-type"].startswith("application/javascript")
    assert rec.size == 1234
    assert rec.scheme == "https" and rec.status == 200


def test_content_length_ausente_vira_desconhecido_e_nao_zero():
    """Zero significaria 'corpo vazio' — que é outra coisa, e afirmativa."""
    rec = Recurso.de_resposta(_Resposta("https://alvo.example/x"), "https://alvo.example/")
    assert rec.size == -1


def test_headers_do_recurso_sao_somente_leitura():
    rec = Recurso.de_resposta(_Resposta("https://a/x", 200, {"A": "1"}), "https://a/")
    with pytest.raises(TypeError):
        rec.headers["a"] = "2"


# ---------- Leitura de corpo ----------

def test_corpo_dentro_do_teto_e_lido_em_memoria():
    resposta = _Resposta("https://a/x.js", 200, {}, b"console.log(1)")
    rec = Recurso.de_resposta(resposta, "https://a/")
    corpo = ler_corpo(rec)
    assert corpo.avaliavel and corpo.dados == b"console.log(1)"
    assert texto_do_corpo(corpo) == "console.log(1)"


def test_corpo_acima_do_teto_devolve_none_e_truncado():
    """Caso da OS: >512KB → None + truncado. Nunca os primeiros 512KB."""
    grande = b"x" * (TETO_CORPO_BYTES + 1)
    rec = Recurso.de_resposta(_Resposta("https://a/g.js", 200, {}, grande), "https://a/")
    corpo = ler_corpo(rec)
    assert corpo.dados is None and corpo.truncado is True
    assert not corpo.avaliavel
    assert "teto" in corpo.motivo


def test_content_length_grande_evita_puxar_os_bytes():
    resposta = _Resposta("https://a/g.bin", 200, {"Content-Length": str(TETO_CORPO_BYTES + 1)})
    rec = Recurso.de_resposta(resposta, "https://a/")
    corpo = ler_corpo(rec)
    assert corpo.truncado and not corpo.avaliavel
    assert resposta.leituras == 0, "não puxa bytes que já sabe que não vai analisar"


def test_segunda_leitura_nao_falha_e_nao_reconsulta():
    """Caso da OS: a leitura do Playwright pode não sobreviver à segunda chamada."""
    resposta = _Resposta("https://a/x.js", 200, {}, b"abc")
    rec = Recurso.de_resposta(resposta, "https://a/")
    assert ler_corpo(rec).dados == b"abc"
    assert ler_corpo(rec).dados == b"abc"
    assert resposta.leituras == 1, "resultado memoizado"


def test_corpo_indisponivel_nao_derruba_e_declara_o_motivo():
    rec = Recurso.de_resposta(_Resposta("https://a/x", 204, {}, explode=True), "https://a/")
    corpo = ler_corpo(rec)
    assert not corpo.avaliavel and "indisponível" in corpo.motivo


def test_recurso_sem_fonte_e_nao_avaliavel():
    rec = Recurso(url="https://a/x", status=200, headers={}, content_type="",
                  size=-1, scheme="https", from_origin=True)
    assert not ler_corpo(rec).avaliavel


def test_texto_de_corpo_nao_avaliavel_e_vazio():
    """Quem não leu não conclui: string vazia, e o chamador checa `avaliavel`."""
    assert texto_do_corpo(Corpo(None, truncado=True)) == ""


def test_bytes_indecodificaveis_nao_derrubam_a_varredura():
    rec = Recurso.de_resposta(_Resposta("https://a/x.bin", 200, {}, b"\xff\xfe\x00abc"),
                              "https://a/")
    assert "abc" in texto_do_corpo(ler_corpo(rec))
