"""VERIFICAÇÃO: utilitários de medição — foco em LIMITES (listas vazias, 1 item)."""
import pytest

from webqa.http_utils import percentiles

pytestmark = pytest.mark.verification


def test_percentis_lista_vazia():
    assert percentiles([]) == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


def test_percentis_um_elemento():
    p = percentiles([100.0])
    assert p["p50"] == p["p95"] == p["p99"] == 100.0


def test_percentis_ordem_nao_importa():
    a = percentiles([300, 100, 200])
    b = percentiles([100, 200, 300])
    assert a == b


def test_p95_maior_ou_igual_p50():
    p = percentiles([float(i) for i in range(1, 101)])
    assert p["p50"] <= p["p95"] <= p["p99"]
