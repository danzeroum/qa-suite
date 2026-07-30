"""Observabilidade: o sistema permite diagnóstico externo?

Verifica sinais observáveis via HTTP: endpoint de saúde, correlação de
requisições (request-id) e erros estruturados — pré-requisitos para
logging/tracing/monitoramento eficazes no backend.
"""
import pytest

pytestmark = pytest.mark.backend

HEALTH_PATHS = ("/health", "/healthz", "/status", "/ping", "/actuator/health", "/api/health")


def test_endpoint_de_saude_existe(client, settings):
    encontrados = []
    for path in HEALTH_PATHS:
        try:
            resp = client.get(settings.target_url + path)
        except Exception:
            continue
        if resp.status_code == 200:
            encontrados.append(path)
    if not encontrados:
        pytest.xfail(
            "Nenhum endpoint de saúde convencional encontrado "
            f"({', '.join(HEALTH_PATHS)}) — monitoramento externo fica limitado."
        )


def test_correlacao_de_requisicoes(home_response):
    """Um ID de correlação no response permite rastrear a requisição nos logs
    (tracing distribuído). Ausência é aceitável, mas registrada como alerta."""
    candidates = ("x-request-id", "x-correlation-id", "x-trace-id",
                  "traceparent", "cf-ray", "x-amzn-requestid")
    if not any(h in home_response.headers for h in candidates):
        pytest.xfail("Sem header de correlação (x-request-id/traceparent) — dificulta rastrear incidentes.")


def test_erro_de_api_e_estruturado(client, settings):
    """Se houver API JSON, erros devem ser estruturados (não HTML cru)."""
    resp = client.get(settings.target_url + "/api/webqa-nao-existe", headers={"Accept": "application/json"})
    if resp.status_code == 404 and "json" in resp.headers.get("content-type", ""):
        assert resp.json(), "Erro JSON vazio"
    else:
        pytest.skip("Alvo não expõe API JSON em /api — teste não aplicável.")
