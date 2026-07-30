"""VERIFICAÇÃO da camada de LLM local (docs/LLM.md, OS-23 v2).

**Nenhum teste aqui toca rede.** O veto de endpoint é exercido com
`getaddrinfo` dublado, e o `Protocol` permite substituir o resumidor por um
fake — que é a razão de o `Protocol` existir (inversão de dependência).

O que estes testes protegem é uma invariante ética, não um comportamento: a
camada de LLM é local, e "local" tem de ser verificável por resolução de nome,
não por inspeção de string. Um endpoint chamado `localhost.atacante.com` resolve
para IP público e passaria por qualquer verificação textual.
"""
from __future__ import annotations

import socket

import pytest

from webqa import gates
from webqa.llm import (
    ESTADOS_NO_PROMPT,
    PREFIXO_REVISAR,
    TEMPERATURA,
    TETO_ACHADOS,
    ResumidorLLM,
    ResumidorLocal,
    achados_para_prompt,
    aplicar_guarda_de_linguagem,
    corpo_da_requisicao,
    validar_endpoint,
)

pytestmark = pytest.mark.verification


def _resolve_para(monkeypatch, *enderecos: str) -> None:
    """Dubla `getaddrinfo` — nenhuma consulta DNS real sai daqui."""
    def falso(host, porta, *args, **kwargs):
        if not enderecos:
            raise socket.gaierror("nome não resolve")
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (e, porta))
                for e in enderecos]
    monkeypatch.setattr(socket, "getaddrinfo", falso)


# ---------- Veto de endpoint: por IP resolvido, nunca por string ----------

@pytest.mark.parametrize("url,ip", [
    ("http://localhost:11434/v1/chat/completions", "127.0.0.1"),
    ("http://127.0.0.1:11434/v1", "127.0.0.1"),
    ("http://ollama.lan:11434/v1", "192.168.1.50"),
    ("http://servidor:8080/v1", "10.0.0.7"),
    ("http://servidor:8080/v1", "172.16.3.9"),
    ("http://[::1]:11434/v1", "::1"),
])
def test_endpoint_local_e_aceito(monkeypatch, url, ip):
    _resolve_para(monkeypatch, ip)
    assert validar_endpoint(url) == url


# Cuidado ao acrescentar caso aqui: as faixas de DOCUMENTAÇÃO da RFC 5737
# (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) respondem True a `is_private`
# em `ipaddress`, porque não são roteáveis. Elas NÃO servem para provar recusa —
# um teste com 203.0.113.10 passa pelo veto e parece um bug no código.
@pytest.mark.parametrize("url,ip", [
    ("https://api.openai.com/v1/chat/completions", "104.18.7.192"),
    ("http://localhost.atacante.example/v1", "93.184.216.34"),
    ("http://ollama-local.example/v1", "8.8.8.8"),
])
def test_endpoint_publico_e_recusado(monkeypatch, url, ip):
    """O segundo e o terceiro casos são o ponto do teste: o NOME parece local.

    Se o veto fosse por string, `localhost.atacante.example` passaria — e a
    invariante "nada sai da máquina" seria uma frase no doc, não uma garantia.
    """
    _resolve_para(monkeypatch, ip)
    with pytest.raises(ValueError, match="nuvem fora de escopo"):
        validar_endpoint(url)


def test_zero_zero_zero_zero_e_recusado(monkeypatch):
    """`0.0.0.0` responde True a `is_private` em `ipaddress` (está em 0.0.0.0/8).

    Fosse a ordem das checagens outra, ele passaria como "rede local" — e
    endereço não especificado não é destino, é curinga de escuta.
    """
    _resolve_para(monkeypatch, "0.0.0.0")
    with pytest.raises(ValueError, match="não especificado"):
        validar_endpoint("http://0.0.0.0:11434/v1")


def test_metadados_de_nuvem_recusado_apesar_de_link_local(monkeypatch):
    """169.254.169.254 é link-local, mas é serviço do provedor, não esta máquina."""
    _resolve_para(monkeypatch, "169.254.169.254")
    with pytest.raises(ValueError, match="nuvem fora de escopo"):
        validar_endpoint("http://metadata.local/v1")


def test_host_com_ip_local_e_publico_e_recusado(monkeypatch):
    """Quem escolhe qual IP usar é o SO. Garantia que depende de sorte não é garantia."""
    _resolve_para(monkeypatch, "192.168.0.10", "93.184.216.34")
    with pytest.raises(ValueError, match="nuvem fora de escopo"):
        validar_endpoint("http://misto.example/v1")


def test_host_que_nao_resolve_e_recusado(monkeypatch):
    _resolve_para(monkeypatch)
    with pytest.raises(ValueError, match="não resolve"):
        validar_endpoint("http://inexistente.invalid/v1")


def test_url_sem_host_e_recusada():
    with pytest.raises(ValueError, match="sem host"):
        validar_endpoint("/v1/chat/completions")


def test_resumidor_local_valida_no_construtor(monkeypatch):
    """Como o `Finding`: não existe instância apontando para a nuvem."""
    _resolve_para(monkeypatch, "104.18.7.192")
    with pytest.raises(ValueError, match="nuvem fora de escopo"):
        ResumidorLocal(endpoint="https://api.openai.com/v1/chat/completions")


# ---------- Payload: `passed` nunca entra ----------

SUMMARY_MISTO = [
    {"test": "checks/a.py::t_ok", "dimension": "backend", "estado": "passed", "detail": ""},
    {"test": "checks/b.py::t_falha", "dimension": "seguranca", "estado": "failed",
     "severidade": "alta", "fase_seguranca": "A", "detail": "credencial exposta"},
    {"test": "checks/c.py::t_alerta", "dimension": "lgpd", "estado": "xfail",
     "detail": "sem Referrer-Policy"},
    {"test": "checks/d.py::t_infra", "dimension": "ux", "estado": "error",
     "detail": "Chromium indisponível"},
    {"test": "checks/e.py::t_pulado", "dimension": "ux", "estado": "skipped",
     "detail": "sem imagens"},
]


def test_passed_nunca_entra_no_payload():
    """Confirmar conformidade por AUSÊNCIA de achado é o erro que a suíte inteira
    existe para não cometer — e um `passed` no prompt convida o modelo a isso."""
    achados = achados_para_prompt(SUMMARY_MISTO)
    assert {a["estado"] for a in achados} == ESTADOS_NO_PROMPT
    assert len(achados) == 3, "entrou algo que não é failed/xfail/error"


def test_payload_leva_severidade_e_fase_quando_existem():
    achados = achados_para_prompt(SUMMARY_MISTO)
    grave = next(a for a in achados if a["test"].endswith("t_falha"))
    assert grave["severidade"] == "alta" and grave["fase_seguranca"] == "A"


def test_teto_de_achados_corta_pelos_menos_graves():
    """Se 80 não couberem tudo, o que fica de fora é o menos grave — nunca o que
    por acaso rodou por último."""
    muitos = (
        [{"test": f"c/x.py::baixa{i}", "estado": "failed", "severidade": "baixa"}
         for i in range(TETO_ACHADOS)]
        + [{"test": "c/x.py::critico", "estado": "failed", "severidade": "alta"}]
    )
    achados = achados_para_prompt(muitos)
    assert len(achados) == TETO_ACHADOS
    assert achados[0]["test"] == "c/x.py::critico"


def test_corpo_da_requisicao_fixa_temperatura_baixa():
    corpo = corpo_da_requisicao(achados_para_prompt(SUMMARY_MISTO), "modelo-x")
    assert corpo["temperature"] == TEMPERATURA == 0.2
    assert corpo["model"] == "modelo-x"
    conteudo = corpo["messages"][1]["content"]
    assert "t_falha" in conteudo
    assert "t_ok" not in conteudo, "recurso `passed` chegou ao corpo da requisição"


# ---------- Guarda de linguagem: marca, não descarta ----------

@pytest.mark.parametrize("texto,rotulo", [
    ("O site está aprovado para produção.", "aprovado"),
    ("A aplicação é segura.", "seguro"),
    ("Sistema certificado quanto à LGPD.", "certificado"),
    ("O alvo está conforme.", "conforme"),
])
def test_linguagem_de_certificacao_e_marcada_e_o_texto_preservado(texto, rotulo):
    saida = aplicar_guarda_de_linguagem(texto)
    assert saida.startswith(PREFIXO_REVISAR)
    assert rotulo in saida
    assert texto in saida, "o texto original tem de sobreviver — marcar não é descartar"


def test_sumario_sem_certificacao_passa_intacto():
    texto = "Três achados de severidade alta. Comece pela credencial exposta."
    assert aplicar_guarda_de_linguagem(texto) == texto


def test_a_palavra_seguranca_nao_dispara_a_guarda():
    """`segur` como radical casaria com 'segurança', que aparece em toda linha
    de um sumário desta suíte — a guarda viraria ruído e seria ignorada."""
    texto = "A dimensão de segurança acusou dois achados; revise as políticas de segurança."
    assert aplicar_guarda_de_linguagem(texto) == texto


# ---------- Gate e Protocol ----------

def test_gate_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv(gates.LLM_ENV, raising=False)
    assert gates.llm_enabled() is False


@pytest.mark.parametrize("valor,esperado", [("1", True), ("0", False), ("true", False)])
def test_gate_so_liga_com_um(monkeypatch, valor, esperado):
    monkeypatch.setenv(gates.LLM_ENV, valor)
    assert gates.llm_enabled() is esperado


def test_gate_de_llm_e_independente_dos_outros(monkeypatch):
    """Autorizar carga não pode ligar IA, e vice-versa."""
    monkeypatch.setenv(gates.LOAD_ENV, "1")
    monkeypatch.setenv(gates.ACTIVE_PROBES_ENV, "1")
    monkeypatch.delenv(gates.LLM_ENV, raising=False)
    assert gates.llm_enabled() is False


def test_fake_satisfaz_o_protocolo_sem_rede():
    """A razão de o `Protocol` existir: teste nenhum precisa de runtime local."""
    class ResumidorFake:
        def resumir(self, resultados: list[dict]) -> str:
            return f"{len(achados_para_prompt(resultados))} achados"

    fake = ResumidorFake()
    assert isinstance(fake, ResumidorLLM)
    assert fake.resumir(SUMMARY_MISTO) == "3 achados"
