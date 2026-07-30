"""VERIFICAÇÃO: guardas de autorização são independentes entre si.

O risco que estes testes cobrem é de acoplamento: autorizar carga NÃO pode
autorizar sondagem ativa (escrever no sistema do alvo) por tabela.
"""
import pytest

from webqa import gates

pytestmark = pytest.mark.verification


def test_gates_desligados_por_default(monkeypatch):
    monkeypatch.delenv(gates.LOAD_ENV, raising=False)
    monkeypatch.delenv(gates.ACTIVE_PROBES_ENV, raising=False)
    assert gates.load_authorized() is False
    assert gates.active_probes_authorized() is False


def test_gate_de_carga_nao_autoriza_sondagem_ativa(monkeypatch):
    monkeypatch.setenv(gates.LOAD_ENV, "1")
    monkeypatch.delenv(gates.ACTIVE_PROBES_ENV, raising=False)
    assert gates.active_probes_authorized() is False


def test_valor_precisa_ser_exatamente_1(monkeypatch):
    for valor in ("0", "true", "yes", ""):
        monkeypatch.setenv(gates.ACTIVE_PROBES_ENV, valor)
        assert gates.active_probes_authorized() is False
    monkeypatch.setenv(gates.ACTIVE_PROBES_ENV, "1")
    assert gates.active_probes_authorized() is True


def test_require_active_probes_pula_sem_autorizacao(monkeypatch):
    monkeypatch.delenv(gates.ACTIVE_PROBES_ENV, raising=False)
    # pytest.skip levanta Skipped, que herda de BaseException — capturar
    # `Exception` deixaria este teste "passar" sendo pulado.
    with pytest.raises(pytest.skip.Exception) as exc:
        gates.require_active_probes()
    assert gates.ACTIVE_PROBES_ENV in str(exc.value)


def test_require_active_probes_libera_com_autorizacao(monkeypatch):
    monkeypatch.setenv(gates.ACTIVE_PROBES_ENV, "1")
    gates.require_active_probes()  # não levanta
