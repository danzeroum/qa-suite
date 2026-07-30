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


# ---- OS-37: autenticação presa à origem do alvo ----

class _SettingsFake:
    target_url = "https://alvo.example"
    timeout_s = 5.0
    user_agent = "WebQA-Suite/teste"
    load_requests = 1
    load_concurrency = 1


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    from webqa import auth, sanitize
    monkeypatch.delenv(auth.USUARIO_ENV, raising=False)
    monkeypatch.delenv(auth.SENHA_ENV, raising=False)
    sanitize.esquecer_valores_sensiveis()
    yield
    sanitize.esquecer_valores_sensiveis()


def test_make_client_sem_ambiente_nao_leva_autenticacao():
    from webqa.http_utils import make_client
    with make_client(_SettingsFake()) as c:
        assert c.auth is None


def test_make_client_com_ambiente_leva_autenticacao_de_origem(monkeypatch):
    from webqa import auth
    from webqa.http_utils import AutenticacaoDeOrigem, make_client
    monkeypatch.setenv(auth.USUARIO_ENV, "u")
    monkeypatch.setenv(auth.SENHA_ENV, "senha-longa-o-bastante")
    with make_client(_SettingsFake()) as c:
        assert isinstance(c.auth, AutenticacaoDeOrigem)


def test_cabecalho_so_vai_para_a_origem_do_alvo():
    """A prova de que a senha NÃO vai para o CDN do axe-core.

    O cliente é de sessão e o mesmo objeto busca `cdnjs.cloudflare.com`; com um
    `httpx.BasicAuth` comum, a senha do operador iria junto.
    """
    import httpx

    from webqa.auth import Credencial
    from webqa.http_utils import AutenticacaoDeOrigem

    autenticacao = AutenticacaoDeOrigem(
        Credencial(usuario="u", senha="senha-longa-o-bastante"), "https://alvo.example")

    def cabecalho_de(url):
        pedido = next(autenticacao.auth_flow(httpx.Request("GET", url)))
        return pedido.headers.get("Authorization")

    assert cabecalho_de("https://alvo.example/pagina") is not None
    assert cabecalho_de("https://cdnjs.cloudflare.com/axe.min.js") is None
    assert cabecalho_de("https://outro.example/politica") is None
    assert cabecalho_de("http://alvo.example/") is None, "http:// puro não leva senha"
