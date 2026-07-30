"""VERIFICAÇÃO (unidade): o alvo fixture serve o que promete e sobe sem flake.

Rápido e sem navegador — roda no quality-gate. O teste de SISTEMA (contrato
completo da dimensão) está em tests/test_alvo_fixture.py e exige Chromium.
"""
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from fixture_target import servir
from fixture_target.servir import CDN_FALSO, TRACKER, AlvoFixture, identidade

pytestmark = pytest.mark.verification

CONTRATO = Path(__file__).resolve().parent.parent / "fixture_target" / "esperado.json"


def _get(url: str):
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 - 127.0.0.1 fixo
        return resp.status, resp.read().decode("utf-8"), resp.headers


# ---------- Subida do servidor ----------

def test_porta_efemera_por_padrao():
    with AlvoFixture() as a, AlvoFixture() as b:
        assert a.porta != b.porta
        assert a.url.startswith("http://127.0.0.1:")


def test_porta_ocupada_nao_vira_flake():
    """Porta ocupada é problema de ambiente; o fixture contorna e serve."""
    bloqueio = socket.socket()
    bloqueio.bind(("127.0.0.1", 0))
    ocupada = bloqueio.getsockname()[1]
    bloqueio.listen(1)
    try:
        with AlvoFixture(porta=ocupada) as alvo:
            assert alvo.porta != ocupada
            status, corpo, _ = _get(alvo.url)
            assert status == 200 and "Loja Fixture" in corpo
    finally:
        bloqueio.close()


# ---------- Violações servidas ----------

@pytest.fixture(scope="module")
def home():
    with AlvoFixture() as alvo:
        status, corpo, headers = _get(alvo.url + "/")
        assert status == 200
        return corpo, headers


def test_pii_na_query_string(home):
    corpo, _ = home
    assert "?email=joao@exemplo.com" in corpo


def test_form_pessoal_em_get(home):
    corpo, _ = home
    assert 'method="get"' in corpo and 'name="email"' in corpo


def test_imagem_sem_alt(home):
    corpo, _ = home
    assert '<img src="/logo.png" width' in corpo and "alt=" not in corpo.split("<form")[0]


def test_script_de_terceiro_sem_sri(home):
    corpo, _ = home
    assert CDN_FALSO in corpo and "integrity=" not in corpo
    assert CDN_FALSO.endswith(".invalid/jquery-3.7.1.min.js"), (
        "o CDN do fixture precisa ser .invalid (RFC 2606): sem dependência externa real"
    )


def test_tracker_disparado_sem_consentimento(home):
    corpo, _ = home
    assert TRACKER in corpo and "googletagmanager.com" in TRACKER


def test_cookie_de_730_dias_e_cookie_de_sessao(home):
    _, headers = home
    cookies = headers.get_all("Set-Cookie") or []
    assert any("_ga=" in c and "Max-Age=63072000" in c for c in cookies)
    assert any(c.startswith("sessionid=") and "Max-Age" not in c for c in cookies)


def test_politica_e_conforme(home):
    """O fixture é não conforme em consentimento, mas CONFORME em transparência."""
    with AlvoFixture() as alvo:
        status, corpo, _ = _get(alvo.url + "/privacidade")
    assert status == 200 and len(corpo) > 1500
    for termo in ("acesso", "correcao", "eliminacao", "portabilidade", "revogar", "DPO"):
        assert termo in corpo, f"política do fixture sem '{termo}'"


def test_recurso_desconhecido_responde_404():
    with AlvoFixture() as alvo:
        try:
            _get(alvo.url + "/.well-known/security.txt")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            pytest.fail("security.txt deveria faltar no fixture (ausência é xfail informativo)")


# ---------- Identidade do alvo (chave do ledger) ----------

def test_identidade_nao_depende_da_porta():
    """A porta é efêmera; se a identidade viesse da URL, a sequência sem flake
    zeraria toda noite e a Fase 2 nunca destravaria."""
    with AlvoFixture() as a, AlvoFixture() as b:
        assert a.porta != b.porta
    assert identidade() == identidade()
    assert identidade().startswith("fixture_target:")


def test_identidade_muda_quando_a_violacao_muda(monkeypatch):
    """Mexeu no que o alvo serve, o alvo é outro — e a sequência recomeça."""
    antes = identidade()
    monkeypatch.setattr(servir, "HOME", servir.HOME.replace('method="get"', 'method="post"'))
    assert identidade() != antes


def test_identidade_ignora_comentario_do_codigo():
    """Só o conteúdo SERVIDO entra no hash: comentário não reinicia a métrica."""
    fonte = Path(servir.__file__).read_text(encoding="utf-8")
    assert "# VIOLACAO" not in identidade()
    assert fonte.count("VIOLACAO") >= 5  # os marcadores seguem no código, fora do hash


# ---------- Sanidade do contrato ----------

def test_contrato_e_json_valido_e_coerente():
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    devem = contrato["devem_falhar"]
    fora = contrato["fora_do_contrato"]
    assert devem, "contrato vazio aprovaria qualquer regressão"
    assert len(devem) == len(set(devem)), "ids duplicados em devem_falhar"
    assert not (set(devem) & set(fora)), "um teste não pode ser esperado e excluído ao mesmo tempo"
    for teste in devem:
        assert "::" in teste, f"id sem '::' não casa com nodeid do pytest: {teste}"
    for motivo in fora.values():
        assert motivo.strip(), "exclusão do contrato exige motivo escrito"
