"""Fixtures compartilhadas de toda a suíte.

Arquitetura em camadas: os testes (checks/) só conhecem estas fixtures;
todo o detalhe de HTTP/navegador vive em webqa/ — baixo acoplamento e
testabilidade da própria suíte (verificação em tests/).
"""
from __future__ import annotations

import warnings

import pytest
from bs4 import BeautifulSoup

from webqa import metricas
from webqa.auth import (
    aviso_de_senha_curta,
    credencial_do_ambiente,
    credenciais_para_playwright,
    verificar_desafio_de_autenticacao,
)
from webqa.config import Settings, load_settings
from webqa.dominio import Recurso
from webqa.http_utils import Timing, make_client, timed_get
from webqa.trackers import LoggedRequest, NetworkLog


@pytest.fixture(scope="session")
def settings() -> Settings:
    cfg = load_settings()
    if not cfg.target_url:
        pytest.exit("Defina target_url em config.yaml ou WEBQA_TARGET_URL.")
    return cfg


@pytest.fixture(scope="session")
def alvo_alcancavel(settings, credencial):
    """O primeiro GET do alvo, e o preflight que o interpreta.

    Uma porta fechada precisa de UMA linha explicando o que fazer, não de
    dezenas de falhas sobre a página de 401. O 401 é tratado aqui, antes de
    qualquer check, e distingue "não há credencial" de "a credencial foi
    recusada" — dois problemas com duas soluções diferentes.

    Vem ANTES do `client` (e não a partir dele) porque há checks que usam o
    cliente sem passar pela `home_response`: se o preflight pendesse da home, o
    primeiro deles ainda reprovaria medindo a página de 401 — que é exatamente a
    cascata confusa que esta fixture existe para eliminar.

    A resposta é devolvida para a `home_response` reaproveitar: preflight que
    gasta um GET a mais contradiz o respeito ao sistema sob teste.
    """
    with make_client(settings) as cliente_de_sondagem:
        resposta = cliente_de_sondagem.get(settings.target_url)
    verificar_desafio_de_autenticacao(resposta.status_code, credencial, settings.target_url)
    return resposta


@pytest.fixture(scope="session")
def client(settings, alvo_alcancavel):
    with make_client(settings) as c:
        yield c


@pytest.fixture(scope="session")
def credencial():
    """Credencial de Basic Auth do ambiente, ou None (alvo anônimo)."""
    cred = credencial_do_ambiente()
    if cred is not None and cred.senha_curta:
        warnings.warn(aviso_de_senha_curta(), stacklevel=1)
    return cred


@pytest.fixture(scope="session")
def home_response(alvo_alcancavel):
    """Resposta da página inicial — reutilizada por dezenas de testes
    para não martelar o alvo (respeito ao sistema sob teste)."""
    alvo_alcancavel.raise_for_status()
    return alvo_alcancavel


@pytest.fixture(scope="session")
def home_timing(client, settings) -> Timing:
    """Latência da home, medida UMA vez e registrada para o consolidado.

    O registro fica na fixture, não nos testes: assim a medida existe mesmo que
    o teste de orçamento passe — e ninguém precisa lembrar de registrar ao
    escrever o próximo teste que consome esta fixture."""
    medida = timed_get(client, settings.target_url)
    metricas.registrar("ttfb_ms", medida.ttfb_ms)
    metricas.registrar("total_ms", medida.total_ms)
    return medida


@pytest.fixture(scope="session")
def soup(home_response) -> BeautifulSoup:
    return BeautifulSoup(home_response.text, "lxml")


# ---------- Navegador (Playwright) ----------

@pytest.fixture(scope="session")
def browser(settings):
    """Instância única de Chromium por sessão (contextos é que são isolados).
    Se o Playwright/Chromium não estiver instalado, os testes 'browser'
    são pulados com instrução clara (falha explicada > falha misteriosa)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")

    with sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except Exception as exc:  # navegador ausente
            pytest.skip(f"Chromium indisponível: rode `python -m playwright install chromium` ({exc}).")
        yield instance
        instance.close()


@pytest.fixture(scope="session")
def credenciais_navegador(settings, credencial):
    """`http_credentials` do contexto Playwright — None quando o acesso é anônimo.

    Kwarg desempacotado (e não `http_credentials=None`) para que a chamada sem
    credencial fique IDÊNTICA à de antes desta OS: alvo anônimo não muda de
    comportamento por causa de um recurso que ele não usa.
    """
    creds = credenciais_para_playwright(credencial, settings.target_url)
    return {"http_credentials": creds} if creds else {}


@pytest.fixture(scope="session")
def browser_page(browser, credenciais_navegador, alvo_alcancavel):
    """Página Chromium real para medir renderização e acessibilidade."""
    page = browser.new_page(**credenciais_navegador)
    yield page
    page.close()


@pytest.fixture(scope="module")
def network_log(browser, settings, credenciais_navegador, alvo_alcancavel) -> NetworkLog:
    """Carrega o alvo em contexto NOVO E VIRGEM e devolve o que a rede revelou.

    Contrato (webqa/trackers.py::NetworkLog): `.requests` (url, resource_type de
    TODA requisição, inclusive as de terceiros) e `.cookies` (cookies do contexto
    após o load).

    Contexto próprio, não a página da sessão: cookie ou consentimento herdado de
    um teste anterior faria o alvo parecer conforme ("já consentiu antes") —
    o pior falso negativo possível numa bateria de consentimento prévio.
    """
    context = browser.new_context(user_agent=settings.user_agent, **credenciais_navegador)
    requests: list[LoggedRequest] = []
    recursos: list[Recurso] = []
    context.on("request", lambda r: requests.append(LoggedRequest(r.url, r.resource_type)))

    def registrar_resposta(resposta) -> None:
        # Só METADADOS aqui. O corpo fica com o Playwright e é lido sob demanda
        # por `dominio.ler_corpo`, em memória e com teto — puxar bytes dentro do
        # handler faria a página inteira residir na RAM sem ninguém ter pedido.
        try:
            recursos.append(Recurso.de_resposta(resposta, settings.target_url))
        except Exception:
            pass    # instrumentação não pode derrubar a observação do alvo

    context.on("response", registrar_resposta)
    page = context.new_page()
    try:
        page.goto(settings.target_url, wait_until="load", timeout=60_000)
        # Tags de analytics costumam disparar depois do load; observar cedo demais
        # produziria aprovação falsa.
        page.wait_for_timeout(2_000)
        yield NetworkLog(
            url=settings.target_url,
            requests=tuple(requests),
            cookies=tuple(context.cookies()),
            recursos=tuple(recursos),
        )
    finally:
        # O contexto morre AQUI, depois do teste: é o que permite a leitura de
        # corpo sob demanda durante a asserção.
        context.close()
