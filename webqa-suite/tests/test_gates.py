"""VERIFICAÇÃO: guardas de autorização são independentes entre si.

O risco que estes testes cobrem é de acoplamento: autorizar carga NÃO pode
autorizar sondagem ativa (escrever no sistema do alvo) por tabela. Com o split
de C1 (descoberta read-only) e C2 (escrita), o mesmo se aplica entre eles: ler o
que não foi linkado não autoriza escrever, e vice-versa.

O caminho negativo é o que dá valor a um gate: um gate que só foi visto liberar
não está provado. Por isso a maioria dos testes aqui exercita o gate DESLIGADO —
`skip`, nunca `fail`, e nunca "passa" — e prova que só o valor exato `"1"` liga.
"""
import pytest

from webqa import gates

pytestmark = pytest.mark.verification


class _EscopoFake:
    """Dublê de `Escopo`: `require_escopo` só depende de `esta_no_escopo(url)`.

    Injetável de propósito — o gate recebe o escopo por parâmetro e não importa
    `webqa.escopo`, então o teste não precisa do módulo nem toca a rede.
    """

    def __init__(self, dentro: bool) -> None:
        self._dentro = dentro

    def esta_no_escopo(self, url: str) -> bool:
        return self._dentro


# valores que NÃO podem ligar nenhum gate — o "quase verdadeiro" que entra num
# compose por descuido é exatamente o que a comparação exata existe para barrar.
NAO_LIGA = ["", "0", "true", "True", "yes", "sim", "2", " 1", "1 "]


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


def test_require_active_probes_usa_o_prefixo_padronizado(monkeypatch):
    monkeypatch.delenv(gates.ACTIVE_PROBES_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception, match=r"\[gate:active_probes\]"):
        gates.require_active_probes()


# ---------- C1: descoberta read-only (WEBQA_DISCOVERY_AUTHORIZED) ----------

def test_discovery_desligado_por_default(monkeypatch):
    monkeypatch.delenv(gates.DISCOVERY_ENV, raising=False)
    assert gates.discovery_authorized() is False


@pytest.mark.parametrize("valor", NAO_LIGA)
def test_discovery_so_liga_com_o_valor_exato_1(monkeypatch, valor):
    """Fail-closed: nenhum quase-verdadeiro autoriza descoberta."""
    monkeypatch.setenv(gates.DISCOVERY_ENV, valor)
    assert gates.discovery_authorized() is False, f"{valor!r} não pode autorizar"


def test_discovery_liga_com_1(monkeypatch):
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    assert gates.discovery_authorized() is True


def test_require_discovery_pula_sem_autorizacao(monkeypatch):
    """Skip (não fail): falta de autorização não é defeito do alvo. E o skip
    carrega o prefixo e o nome da variável, para o operador saber o que exportar."""
    monkeypatch.delenv(gates.DISCOVERY_ENV, raising=False)
    with pytest.raises(pytest.skip.Exception) as exc:
        gates.require_discovery()
    mensagem = str(exc.value)
    assert "[gate:discovery]" in mensagem
    assert gates.DISCOVERY_ENV in mensagem


def test_require_discovery_libera_com_autorizacao(monkeypatch):
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    gates.require_discovery()  # não levanta


def test_autorizar_descoberta_nao_autoriza_escrita(monkeypatch):
    """O coração do split C1×C2: ler o não-linkado não autoriza escrever."""
    monkeypatch.setenv(gates.DISCOVERY_ENV, "1")
    monkeypatch.delenv(gates.ACTIVE_PROBES_ENV, raising=False)
    assert gates.active_probes_authorized() is False
    with pytest.raises(pytest.skip.Exception):
        gates.require_active_probes()


def test_autorizar_escrita_nao_autoriza_descoberta(monkeypatch):
    """E a volta: o gate de escrita não liga o de descoberta por tabela."""
    monkeypatch.setenv(gates.ACTIVE_PROBES_ENV, "1")
    monkeypatch.delenv(gates.DISCOVERY_ENV, raising=False)
    assert gates.discovery_authorized() is False
    with pytest.raises(pytest.skip.Exception):
        gates.require_discovery()


# ---------- parada de emergência (WEBQA_ACTIVE_PROBES_KILL) ----------

def test_kill_switch_desligado_por_default(monkeypatch):
    monkeypatch.delenv(gates.KILL_ENV, raising=False)
    assert gates.kill_switch_active() is False


@pytest.mark.parametrize("valor", NAO_LIGA)
def test_kill_switch_so_liga_com_o_valor_exato_1(monkeypatch, valor):
    monkeypatch.setenv(gates.KILL_ENV, valor)
    assert gates.kill_switch_active() is False, f"{valor!r} não pode ativar"


def test_kill_switch_liga_com_1(monkeypatch):
    monkeypatch.setenv(gates.KILL_ENV, "1")
    assert gates.kill_switch_active() is True


def test_kill_switch_e_independente_dos_gates(monkeypatch):
    """A parada de emergência não é gate de autorização e não vaza para eles."""
    monkeypatch.setenv(gates.KILL_ENV, "1")
    for env in (gates.DISCOVERY_ENV, gates.ACTIVE_PROBES_ENV, gates.LOAD_ENV):
        monkeypatch.delenv(env, raising=False)
    assert gates.discovery_authorized() is False
    assert gates.active_probes_authorized() is False
    assert gates.load_authorized() is False


# ---------- escopo: ortogonal aos gates (WEBQA_* não entra aqui) ----------

def test_require_escopo_pula_fora_do_escopo():
    """URL fora da allowlist → skip com prefixo e a URL, sem tocar env nem rede."""
    with pytest.raises(pytest.skip.Exception) as exc:
        gates.require_escopo(_EscopoFake(dentro=False), "https://alheio.example/x")
    mensagem = str(exc.value)
    assert "[gate:escopo]" in mensagem
    assert "https://alheio.example/x" in mensagem


def test_require_escopo_libera_dentro_do_escopo():
    gates.require_escopo(_EscopoFake(dentro=True), "https://meu-alvo.example/x")  # não levanta


def test_require_escopo_nao_depende_de_gate(monkeypatch):
    """Ortogonalidade: mesmo com todo gate aberto, fora do escopo ainda pula —
    autorização de técnica não é autorização de host."""
    for env in (gates.DISCOVERY_ENV, gates.ACTIVE_PROBES_ENV, gates.LOAD_ENV):
        monkeypatch.setenv(env, "1")
    with pytest.raises(pytest.skip.Exception, match=r"\[gate:escopo\]"):
        gates.require_escopo(_EscopoFake(dentro=False), "https://alheio.example/y")


def test_require_escopo_consulta_o_escopo_uma_vez():
    """`require_escopo` decide só por `esta_no_escopo`, e o chama de fato — um
    dublê que conta a chamada prova que a decisão não veio de outra fonte."""
    chamadas = []

    class _Espiao:
        def esta_no_escopo(self, url):
            chamadas.append(url)
            return False

    with pytest.raises(pytest.skip.Exception):
        gates.require_escopo(_Espiao(), "https://alvo.example/z")
    assert chamadas == ["https://alvo.example/z"]
