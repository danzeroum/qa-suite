"""VERIFICAÇÃO: a fronteira rede-local × rede-pública (regra da casa §2.11).

Duas vezes no mesmo par de OS um dublê local escondeu um limite real, e as duas
pela mesma causa estrutural: `PoliteFetcher.preparar` retorna ANTES de tocar no
`robots.txt` quando o alvo é local, então contra `127.0.0.1` todo o caminho a
jusante é inalcançável — e o ensaio sai verde sem ter executado a linha que
interessa.

O que este arquivo prova, e o que ele NÃO prova, dito de frente:

* **prova** que nenhum consumidor da fronteira escapa de ter o ramo PÚBLICO
  exercitado, e que consumidor novo não entra em silêncio;
* **prova** que cada fronteira de fato discrimina — uma que respondesse sempre a
  mesma coisa passaria em todos os testes de hoje e não seria fronteira nenhuma;
* **não prova** que alguém validou contra host real. Os testes de `tests/` são
  livres de rede por regra da casa, e fingir o contrário seria justamente a
  garantia falsa que a §2.11 combate. Essa metade é humana e mora na regra.
"""
from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
BIBLIOTECA = RAIZ / "webqa"
TESTES = RAIZ / "tests"

# Símbolos que decidem "este host é nosso ou de terceiro". Quem importa um deles
# está consumindo a fronteira, e passa a dever cobertura do ramo público.
SIMBOLOS_DA_FRONTEIRA = ("host_e_local", "ip_e_local", "ips_de")

# Registro EXPLÍCITO: módulo da biblioteca → testes que exercitam o ramo público.
#
# Explícito de propósito, como a lista de derivadores da OS-34: derivá-lo do
# código faria a cobertura encolher junto com o que ela deveria vigiar. Aqui a
# divergência REPROVA, nos dois sentidos — consumidor sem entrada (o caso que
# impede a terceira ocorrência) e entrada órfã (registro que envelhece mente).
FRONTEIRAS_DE_REDE: dict[str, tuple[str, ...]] = {
    "webqa/etiqueta.py": (
        "test_alvo_de_rede_local_e_isento_e_nao_consulta_robots",
        "test_robots_de_alvo_protegido_com_credencial_e_lido",
        "test_robots_de_terceiro_e_consultado_anonimo",
    ),
    "webqa/auth.py": (
        "test_credencial_nao_vai_em_http_puro",
        "test_localidade_e_decidida_por_ip_resolvido_nao_por_texto",
    ),
    "webqa/llm.py": (
        "test_endpoint_publico_e_recusado",
    ),
    # evidencias consome a fronteira para decidir se um PNG pode chegar ao disco
    # (R19). O ramo que precisa de prova é o PÚBLICO — alvo real sem opt-in NÃO
    # grava —, porque é o único em que um vazamento de pixel é possível.
    "webqa/evidencias.py": (
        "test_alvo_fabricado_e_reconhecido_e_alvo_real_nao",
        "test_sem_optin_alvo_real_NAO_pode_gravar_png",
    ),
    # escopo consome `ips_de` de um jeito diferente dos outros três: não decide
    # local × terceiro, e sim POSSE — se os IPs do host ainda são os do
    # carregamento. O ramo que precisa de prova é a divergência (takeover), e é
    # ela que estes testes exercitam, em tests/test_escopo.py.
    "webqa/escopo.py": (
        "test_divergencia_de_ip_e_detectada_como_takeover",
        "test_posse_ok_quando_o_ip_bate",
        "test_falha_de_resolucao_agora_e_nao_posse_sem_excecao",
    ),
}


def consumidores_da_fronteira(pasta: Path) -> set[str]:
    """Módulos que IMPORTAM a decisão local × público, por AST.

    Por AST e não por texto: um símbolo citado em docstring ou comentário explica,
    não consome — e reprovar quem explica ensina a não explicar.
    """
    achados: set[str] = set()
    for arquivo in sorted(pasta.glob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ImportFrom):
                continue
            if any(alias.name in SIMBOLOS_DA_FRONTEIRA for alias in no.names):
                achados.add(f"{pasta.name}/{arquivo.name}")
    return achados


def _funcoes_de_teste() -> set[str]:
    nomes: set[str] = set()
    for arquivo in sorted(TESTES.glob("test_*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
                nomes.add(no.name)
    return nomes


# ---------- o detector, provado antes de ser usado ----------

def test_o_detector_acha_consumidor_plantado(tmp_path):
    """Detector que nunca detectou violação plantada não está provado."""
    (tmp_path / "novo.py").write_text(
        "from webqa.rede import host_e_local\n\ndef f(h):\n    return host_e_local(h, 80)\n",
        encoding="utf-8")
    assert consumidores_da_fronteira(tmp_path) == {f"{tmp_path.name}/novo.py"}


def test_o_detector_ignora_mencao_em_prosa(tmp_path):
    """Citar `host_e_local` numa docstring é explicar, não consumir."""
    (tmp_path / "prosa.py").write_text(
        '"""Este módulo NÃO usa host_e_local nem ips_de."""\n# nem ip_e_local aqui\n',
        encoding="utf-8")
    assert consumidores_da_fronteira(tmp_path) == set()


# ---------- Guarda 1: registro 1:1 com a realidade ----------

def test_todo_consumidor_da_fronteira_esta_no_registro():
    """Consumidor novo sem entrada REPROVA — é o que impede a terceira ocorrência.

    Quem acrescentar um consumo da distinção local × público é obrigado, no mesmo
    PR, a dizer qual teste prova o ramo público dele. Sem isso, a próxima
    fronteira nasce coberta só por loopback, que é como as duas anteriores
    nasceram.
    """
    reais = consumidores_da_fronteira(BIBLIOTECA)
    registrados = set(FRONTEIRAS_DE_REDE)

    faltando = reais - registrados
    assert not faltando, (
        f"consumidor(es) da fronteira fora do registro: {sorted(faltando)}. "
        "Acrescente ao FRONTEIRAS_DE_REDE nomeando o teste que exercita o ramo "
        "PÚBLICO — ver regra da casa §2.11.")

    orfas = registrados - reais
    assert not orfas, (
        f"entrada(s) órfã(s) no registro: {sorted(orfas)}. O módulo deixou de "
        "consumir a fronteira; registro que envelhece mente sobre a cobertura.")


def test_os_testes_nomeados_no_registro_existem():
    """Sentinela da OS-34: registro que aponta para teste renomeado não cobre nada."""
    existentes = _funcoes_de_teste()
    perdidos = [
        f"{modulo} → {nome}"
        for modulo, nomes in FRONTEIRAS_DE_REDE.items()
        for nome in nomes
        if nome not in existentes
    ]
    assert not perdidos, (
        "teste nomeado no registro não existe mais: " + "; ".join(perdidos))


# ---------- Guarda 2: a fronteira discrimina de fato ----------

def _resolve_para(monkeypatch, ip: str) -> None:
    """Dubla `getaddrinfo` — nenhuma consulta DNS real sai daqui.

    Mesma técnica de `tests/test_etiqueta.py` e `tests/test_llm.py`: é o único
    jeito de exercitar o ramo público sem tocar a rede.
    """
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, p))])


def _decisao_etiqueta(url: str) -> bool:
    from webqa.etiqueta import PoliteFetcher

    return PoliteFetcher("WebQA/teste").isento(url)


def _decisao_credencial(url: str) -> bool:
    from webqa.auth import pode_enviar_credencial

    # `http://` de propósito: em `https` a resposta é sempre True, e a
    # parametrização "mediria" uma decisão que não depende da fronteira.
    return pode_enviar_credencial(url, "http://alvo.example")


def _decisao_endpoint(url: str) -> bool:
    from webqa.llm import validar_endpoint

    try:
        validar_endpoint(url)
        return True
    except ValueError:
        return False


# (rótulo, função de decisão, URL no esquema em que a fronteira importa)
FRONTEIRAS_EXERCITAVEIS = [
    ("etiqueta.isento", _decisao_etiqueta, "http://alvo.example/"),
    ("auth.pode_enviar_credencial", _decisao_credencial, "http://alvo.example/"),
    ("llm.validar_endpoint", _decisao_endpoint, "http://alvo.example:11434/v1"),
]


@pytest.mark.parametrize("rotulo,decidir,url", FRONTEIRAS_EXERCITAVEIS,
                         ids=[f[0] for f in FRONTEIRAS_EXERCITAVEIS])
def test_a_fronteira_decide_diferente_para_host_local_e_publico(monkeypatch, rotulo, decidir, url):
    """Fronteira que responde sempre o mesmo não é fronteira.

    Passaria em todos os testes de hoje — cada um deles fixa UM lado — e só
    apareceria contra alvo real, que é exatamente o modo de falha que a §2.11
    existe para impedir.
    """
    _resolve_para(monkeypatch, "127.0.0.1")
    local = decidir(url)

    _resolve_para(monkeypatch, "93.184.216.34")
    publico = decidir(url)

    assert local != publico, (
        f"{rotulo} devolveu {local!r} para host local E para host público — "
        "a distinção deixou de existir (regra da casa §2.11).")


def test_o_curto_circuito_da_isencao_esta_documentado():
    """A causa raiz das duas ocorrências, fixada no fonte.

    `preparar` retorna antes de buscar o `robots.txt` quando o alvo é local.
    Quem for mexer ali precisa encontrar o aviso no lugar, não no histórico do
    git — a prosa é o detector, segundo a própria §2.10.
    """
    fonte = (RAIZ / "webqa" / "etiqueta.py").read_text(encoding="utf-8")
    assert "§2.11" in fonte, (
        "o curto-circuito da isenção perdeu a referência à regra que ele originou")
