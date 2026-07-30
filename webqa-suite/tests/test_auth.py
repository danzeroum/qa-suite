"""VERIFICAÇÃO: credencial de Basic Auth — a invariante e as duas fronteiras.

Três coisas são provadas aqui, e nenhuma delas é "o httpx sabe fazer Basic Auth":

1. **a invariante** — não existe `Credencial` cuja senha não esteja registrada
   para mascaramento (irmã da invariante do `Finding`);
2. **a fronteira de origem** — a senha não vai para o CDN do axe-core nem para o
   host da política de privacidade, que o MESMO cliente de sessão visita;
3. **a fronteira de esquema** — a senha não trafega em `http://` claro, exceto
   contra a rede local (o alvo fixture), decidida por IP resolvido.

Nenhum teste toca rede: `pode_enviar_credencial` recebe o resolvedor por
parâmetro, e o preflight recebe um status, não uma resposta.
"""
import base64

import pytest

from webqa import auth, sanitize

pytestmark = pytest.mark.verification

USUARIO = "operador"
SENHA = "s3nh4-comprida-o-suficiente"


@pytest.fixture(autouse=True)
def registro_limpo(monkeypatch):
    """Nem o ambiente do dev nem o caso anterior podem vazar para este."""
    monkeypatch.delenv(auth.USUARIO_ENV, raising=False)
    monkeypatch.delenv(auth.SENHA_ENV, raising=False)
    sanitize.esquecer_valores_sensiveis()
    yield
    sanitize.esquecer_valores_sensiveis()


def _com_ambiente(monkeypatch, usuario=USUARIO, senha=SENHA):
    monkeypatch.setenv(auth.USUARIO_ENV, usuario)
    monkeypatch.setenv(auth.SENHA_ENV, senha)


# ---------- Leitura do ambiente ----------

def test_sem_variaveis_de_ambiente_nao_ha_credencial():
    assert auth.credencial_do_ambiente() is None


def test_credencial_nasce_do_ambiente(monkeypatch):
    _com_ambiente(monkeypatch)
    cred = auth.credencial_do_ambiente()
    assert cred is not None
    assert cred.usuario == USUARIO


@pytest.mark.parametrize("presente", [auth.USUARIO_ENV, auth.SENHA_ENV])
def test_configuracao_pela_metade_falha_nomeando_a_variavel(monkeypatch, presente):
    """Cair para anônimo em silêncio reencenaria a cascata de 401 que a OS resolve."""
    monkeypatch.setenv(presente, "algum-valor")
    with pytest.raises(ValueError, match="pela metade"):
        auth.credencial_do_ambiente()


def test_ambiente_injetado_nao_le_os_environ():
    cred = auth.credencial_do_ambiente({auth.USUARIO_ENV: "u", auth.SENHA_ENV: "p"})
    assert cred is not None and cred.usuario == "u"


# ---------- A invariante ----------

def test_credencial_nasce_registrada_para_mascaramento():
    """Irmã de `test_finding_nasce_com_a_evidencia_mascarada`.

    O registro acontece no CONSTRUTOR: nenhuma borda de escrita precisa lembrar
    de fazê-lo, e por isso nenhuma pode esquecer.
    """
    auth.Credencial(usuario=USUARIO, senha=SENHA)
    assert SENHA not in sanitize.sanitize_text(f"falhou com a senha {SENHA} aqui")


def test_credencial_valida_nao_expoe_senha_em_claro():
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    assert not cred.expoe_senha_em_claro


def test_credencial_vazia_e_recusada():
    with pytest.raises(ValueError, match="incompleta"):
        auth.Credencial(usuario=USUARIO, senha="")


def test_senha_curta_e_aceita_e_apenas_avisada():
    """Decisão registrada: vazar é pior que embaralhar — nunca recusar."""
    cred = auth.Credencial(usuario="u", senha="123")
    assert cred.senha_curta
    assert "123" not in sanitize.sanitize_text("p95=123ms")


# ---------- O repr que não vaza ----------

def test_repr_da_credencial_nao_mostra_a_senha():
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    assert SENHA not in repr(cred)
    assert "[SENHA]" in repr(cred)


def test_interpolacao_e_formatacao_nao_mostram_a_senha():
    """f-string, %s, .format e — o caso que mais pega — repr de um contêiner.

    As formas antigas de interpolação estão aqui DE PROPÓSITO: o que se prova é
    que nenhuma delas alcança a senha, e reescrevê-las como f-string apagaria
    justamente os caminhos sob teste.
    """
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    antigas = ("%s" % cred, "{}".format(cred))  # noqa: UP031, UP032
    for texto in (f"{cred}", *antigas, repr({"c": cred}), str([cred])):
        assert SENHA not in texto


def test_credenciais_do_navegador_tem_repr_redigido():
    """`--showlocals` num erro de fixture é a saída que a varredura do laudo não cobre."""
    creds = auth.credenciais_para_playwright(
        auth.Credencial(usuario=USUARIO, senha=SENHA), "https://alvo.example"
    )
    assert SENHA not in repr(creds)
    assert creds["password"] == SENHA, "o dict ainda precisa servir ao Playwright"


# ---------- Variantes: o que faz a varredura do arquivo valer ----------

def test_variantes_cobrem_base64_userinfo_json_html_e_url():
    formas = auth.variantes_da_senha("joao", 'a"b&c d')
    par = 'joao:a"b&c d'
    assert 'a"b&c d' in formas
    assert par in formas
    assert base64.b64encode(par.encode()).decode() in formas
    assert 'a\\"b&c d' in formas, "forma escapada para JSON"
    assert "a&quot;b&amp;c d" in formas, "forma escapada para HTML"
    assert "a%22b%26c%20d" in formas, "forma percent-encoded"


def test_variantes_nao_repetem_nem_trazem_vazio():
    formas = auth.variantes_da_senha("u", "simples")
    assert len(formas) == len(set(formas))
    assert all(formas)


def test_cabecalho_basic_segue_o_rfc_7617():
    cred = auth.Credencial(usuario="joão", senha="çéu:2")
    esperado = base64.b64encode("joão:çéu:2".encode()).decode("ascii")
    assert cred.cabecalho_basic == f"Basic {esperado}"


# ---------- Origem ----------

def test_origem_ignora_credencial_embutida():
    assert auth.origem_de("https://u:p@alvo.example/x") == "https://alvo.example"


def test_origem_normaliza_porta_padrao():
    assert auth.origem_de("https://a.example:443/x") == auth.origem_de("https://a.example/x")
    assert auth.origem_de("http://a.example:80") == "http://a.example"


def test_origem_preserva_porta_nao_padrao_e_ipv6():
    assert auth.origem_de("http://[::1]:8130/x") == "http://[::1]:8130"


# ---------- A fronteira que impede o vazamento para terceiro ----------

ORIGEM = "https://alvo.example"


def test_credencial_vai_para_a_origem_do_alvo():
    assert auth.pode_enviar_credencial("https://alvo.example/pagina", ORIGEM)


def test_credencial_nao_vai_para_o_cdn_do_axe():
    """O MESMO cliente de sessão busca o axe-core no CDN (checks/ux/test_acessibilidade)."""
    assert not auth.pode_enviar_credencial(
        "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js", ORIGEM
    )


def test_credencial_nao_vai_para_o_host_da_politica():
    assert not auth.pode_enviar_credencial("https://outro.example/privacidade", ORIGEM)


def test_credencial_nao_vai_em_http_puro():
    """`test_http_redireciona_para_https` bate no alvo em http:// de propósito."""
    assert not auth.pode_enviar_credencial(
        "http://alvo.example/", "http://alvo.example", e_local=lambda h, p: False
    )


def test_credencial_vai_em_http_para_alvo_local():
    """O alvo fixture é `http://127.0.0.1:porta` — sem isto, nada seria testável."""
    assert auth.pode_enviar_credencial(
        "http://127.0.0.1:8130/x", "http://127.0.0.1:8130", e_local=lambda h, p: True
    )


def test_localidade_e_decidida_por_ip_resolvido_nao_por_texto():
    """Casar 'localhost' por string autorizaria mandar senha para um host público."""
    vistos = []

    def resolvedor(host, porta):
        vistos.append((host, porta))
        return False

    auth.pode_enviar_credencial("http://localhost:9/x", "http://localhost:9", e_local=resolvedor)
    assert vistos == [("localhost", 9)]


# ---------- Preflight ----------

def test_preflight_com_200_nao_interrompe():
    assert auth.verificar_desafio_de_autenticacao(200, None, "https://a.example") is None


def test_preflight_401_sem_credencial_nomeia_as_variaveis():
    # `Exit` herda de BaseException: capturar Exception deixaria o teste passar
    # sem provar nada (mesma armadilha coberta em tests/test_gates.py).
    with pytest.raises(pytest.exit.Exception) as erro:
        auth.verificar_desafio_de_autenticacao(401, None, "https://a.example")
    assert auth.USUARIO_ENV in str(erro.value)
    assert auth.SENHA_ENV in str(erro.value)


def test_preflight_401_com_credencial_diz_que_foi_rejeitada():
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    with pytest.raises(pytest.exit.Exception) as erro:
        auth.verificar_desafio_de_autenticacao(401, cred, "https://a.example")
    assert "recusou" in str(erro.value)


def test_mensagens_do_preflight_nunca_contem_a_senha():
    cred = auth.Credencial(usuario=USUARIO, senha=SENHA)
    alvo = f"https://{USUARIO}:{SENHA}@a.example/x"
    for mensagem in (auth.orientacao_sem_credencial(alvo),
                     auth.orientacao_credencial_rejeitada(alvo),
                     auth.aviso_de_senha_curta()):
        assert SENHA not in mensagem
    assert not cred.expoe_senha_em_claro
