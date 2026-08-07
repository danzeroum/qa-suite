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
    credenciais_para_playwright,
    credencial_do_ambiente,
    origem_de,
    verificar_desafio_de_autenticacao,
)
from webqa.config import Settings, load_settings
from webqa.dominio import Recurso
from webqa.etiqueta import PoliteFetcher
from webqa.http_utils import Timing, make_client, timed_get
from webqa.navegacao import percorrer
from webqa.navegador import engines_configurados
from webqa.rede_simulada import carregar_perfis_de_rede
from webqa.trackers import LoggedRequest, NetworkLog
from webqa.viewports import carregar_perfis, opcoes_de_contexto


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

    O desfecho é REGISTRADO no laudo (E3). "O alvo foi alcançado?" é estado de
    SESSÃO, e a contagem de desfechos não o reconstrói: contra uma porta fechada,
    os checks que fazem a requisição no corpo (pytest-bdd) terminam em `failed` e
    os que dependem desta fixture em `error` — quem lesse só a contagem veria
    "violações" sobre um alvo que ninguém alcançou. O registro vive em
    webqa/report.py, e não aqui, porque este arquivo não viaja no wheel.
    """
    from webqa.report import registrar_preflight

    try:
        with make_client(settings) as cliente_de_sondagem:
            resposta = cliente_de_sondagem.get(settings.target_url)
    except Exception as erro:   # noqa: BLE001 - qualquer falha de transporte é "não alcançado"
        registrar_preflight(False, f"{type(erro).__name__}: {erro}")
        raise
    registrar_preflight(True, f"HTTP {resposta.status_code}")
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

# As engines a exercitar são decididas no import (WEBQA_BROWSER_ENGINES; default
# chromium). Parametriza-se SÓ quando há mais de uma: com uma engine, o fixture
# não é parametrizado e os node ids ficam limpos (`::test_x`, não `::test_x[chromium]`),
# preservando o contrato 1:1 do alvo fixture (esperado.json, §2.8) sem tocá-lo. A
# matriz completa (noturno) aceita o sufixo `[engine]` — é onde ele faz sentido.
_ENGINES = engines_configurados()


@pytest.fixture(scope="session")
def playwright_sessao():
    """UMA instância de Playwright para a sessão inteira.

    Existe porque a família `gui_compat` precisa de DUAS engines vivas ao mesmo
    tempo, dentro de um teste só (o nodeid é único; a comparação entre engines
    acontece no corpo). Abrir um segundo `sync_playwright()` no mesmo processo
    para conseguir isso não é opção: a API síncrona mantém um despachante por
    instância, e dois no mesmo thread disputam o mesmo laço.

    Fixture separada, e não uma dentro da outra, para que `browser` continue
    sendo o que sempre foi — uma engine por vez, parametrizada.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def motores_gui(playwright_sessao):
    """{engine: Browser} das engines configuradas que ESTÃO instaladas.

    Devolve o que conseguiu abrir, e o chamador decide o que fazer com o
    tamanho: com menos de duas não há comparação possível, e o check pula
    dizendo quantas havia (`webqa/compatibilidade.py::motivo_de_pular`).
    Preencher a lacuna com a engine que existe daria sempre verde — comparar uma
    engine consigo mesma é sempre verde, e esse verde seria indistinguível do
    legítimo.

    Engine ausente é registrada pelo nome: o aceite do noturno exige que a soma
    de executados e pulados feche, e um skip anônimo faz uma engine sumir da
    conta sem ninguém notar.
    """
    abertos, ausentes = {}, {}
    for engine in _ENGINES:
        try:
            abertos[engine] = getattr(playwright_sessao, engine).launch()
        except Exception as exc:       # engine sem binário instalado
            ausentes[engine] = str(exc).splitlines()[0][:160]
    try:
        yield {"abertos": abertos, "ausentes": ausentes}
    finally:
        for instancia in abertos.values():
            instancia.close()


@pytest.fixture(scope="session", params=_ENGINES if len(_ENGINES) > 1 else None)
def browser(request, settings, playwright_sessao):
    """Instância de navegador por sessão, uma por engine configurada (contextos é
    que são isolados). As engines vêm de `WEBQA_BROWSER_ENGINES` (default só
    `chromium`; o noturno roda a matriz chromium/firefox/webkit — C3).

    Playwright ausente ou engine sem binário instalado vira SKIP com instrução
    (falha explicada > falha misteriosa). Engine não instalada nunca conta como
    aprovação — o teste é pulado, não passa em silêncio."""
    engine = getattr(request, "param", _ENGINES[0])
    # A instância de Playwright vem de `playwright_sessao`, e não de um
    # `sync_playwright()` próprio: a API síncrona mantém um despachante por
    # instância, e uma segunda no mesmo processo estoura com "Sync API inside the
    # asyncio loop" assim que outra fixture (`motores_gui`) abre a dela. Uma só,
    # partilhada, é o que permite a comparação entre engines existir.
    try:
        instance = getattr(playwright_sessao, engine).launch()
    except Exception as exc:  # engine ausente/sem binário
        pytest.skip(f"{engine} indisponível: rode "
                    f"`python -m playwright install {engine}` ({exc}).")
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


@pytest.fixture(scope="session")
def perfis_gui():
    """Perfis de viewport de `data/gui-perfis.yaml`.

    Fixture, e não import no check: o alvo do check é o que MEDIR, não de
    onde a configuração vem. Sessão porque o YAML não muda no meio da
    execução — reler por teste seria I/O sem pergunta correspondente.
    """
    return carregar_perfis()


@pytest.fixture(scope="session")
def perfis_de_rede():
    """Perfis de rede e CPU de `data/gui-perfis.yaml` (OS-50).

    Fixture pelo mesmo motivo que `perfis_gui`: o alvo do check é o que MEDIR,
    não de onde a configuração vem. Sessão porque o YAML não muda no meio da
    execução.
    """
    return carregar_perfis_de_rede()


def _contextos_de_gui(browser, settings, credenciais_navegador):
    """Implementação ÚNICA das fixtures de contexto de GUI.

    Uma só, e as duas fixtures abaixo apenas a delegam, porque a diferença entre
    elas é só o escopo: há check que quer um contexto por teste e há check que
    precisa de UMA observação partilhada — a caminhada de foco alimenta três
    vereditos, e percorrer a página três vezes pagaria três vezes pela mesma
    observação, com o risco extra de as três discordarem num alvo dinâmico.

    Duas cópias deste corpo divergiriam no primeiro campo novo, e a divergência
    apareceria como um check isolando e o outro não.
    """
    contextos = []

    def abrir(viewport=None, **opcoes):
        base = {"user_agent": settings.user_agent, **credenciais_navegador}
        # A engine é passada porque a tradução do perfil DEPENDE dela (o Firefox
        # recusa `is_mobile`) — e a decisão de como lidar com isso vive em
        # `webqa/viewports.py`, não aqui. Esta fixture segue casca fina.
        contexto = browser.new_context(
            **opcoes_de_contexto(viewport, engine=browser.browser_type.name, **base, **opcoes))
        contextos.append(contexto)
        return contexto.new_page()

    try:
        yield abrir
    finally:
        # `finally`, e não depois do yield: teste que estoura no meio não pode
        # deixar contexto de navegador vazando para o resto da sessão.
        for contexto in contextos:
            contexto.close()


@pytest.fixture()
def contexto_gui(browser, settings, credenciais_navegador, alvo_alcancavel):
    """Fábrica de páginas em contexto NOVO — uma por variação de GUI.

    Devolve `abrir(viewport=..., **opcoes)`, que abre um `browser.new_context`
    próprio e o fecha no fim do teste. Todo check de `gui` passa por aqui, e
    **nenhum deles toca `browser_page`**.

    A regra não é higiene: `browser_page` é de SESSÃO e é a mesma página que
    `checks/frontend/test_rendering.py` usa para medir FCP, LCP e CLS. Um check
    de GUI que mudasse o viewport ou o tema nela deixaria as Web Vitals das
    outras dimensões medidas num viewport que ninguém declarou — e o número
    sairia errado sem nada ficar vermelho (R20). É a mesma lição que já fez o
    `network_log` nascer com contexto virgem: estado herdado de um teste
    anterior é o pior falso resultado possível, porque é silencioso.

    As opções vêm de `webqa/viewports.py::opcoes_de_contexto`, que é pura — o
    detalhe vive na biblioteca, os checks só conhecem esta fixture.
    """
    yield from _contextos_de_gui(browser, settings, credenciais_navegador)


@pytest.fixture(scope="module")
def contexto_gui_modulo(browser, settings, credenciais_navegador, alvo_alcancavel):
    """A mesma fábrica, viva pelo módulo inteiro.

    Existe para a observação CARA e partilhada: a caminhada de foco percorre a
    página com Tab, alimenta três critérios e mexe no estado do navegador —
    refazê-la por teste seria pagar três vezes por uma observação só. Mesma
    doutrina de `home_response` nas dimensões HTTP.

    Continua sendo contexto PRÓPRIO: partilhar entre testes do mesmo módulo não
    é o mesmo que partilhar com `browser_page`, que atende outras dimensões.
    """
    yield from _contextos_de_gui(browser, settings, credenciais_navegador)


@pytest.fixture(scope="session")
def paginas_internas(browser, settings, credencial, credenciais_navegador, alvo_alcancavel):
    """Área autenticada percorrida seguindo SÓ o que a aplicação oferece (OS-38).

    Contrato (`webqa/navegacao.py`): cada `Pagina` traz a `origem` do endereço
    que levou até ela. Página que ninguém linkou não aparece aqui — não porque
    foi filtrada, mas porque não existe caminho no programa que fabrique um
    endereço. Adivinhar rota é Fase C, e continua desligada.

    O DOM é lido RENDERIZADO: link que só existe depois do JavaScript é link que
    o usuário vê, e ignorá-lo faria a exploração parecer disciplinada quando na
    verdade estaria só cega.
    """
    contexto = browser.new_context(user_agent=settings.user_agent, **credenciais_navegador)
    pagina = contexto.new_page()

    def abrir(url):
        resposta = pagina.goto(url, wait_until="load", timeout=60_000)
        return (resposta.status if resposta else 0), pagina.content()

    fetcher = PoliteFetcher(settings.user_agent, timeout_s=settings.timeout_s,
                            credencial=credencial,
                            origem_do_alvo=origem_de(settings.target_url))
    veredito = fetcher.preparar(settings.target_url)
    try:
        if veredito.bloqueado:
            # Etiqueta bloqueou: devolve lista vazia com o motivo no laudo, em vez
            # de percorrer assim mesmo. Ausência de análise nunca vira atestado.
            yield []
        else:
            yield percorrer(settings.target_url, abrir,
                            teto=settings.crawl_max_pages,
                            pode_acessar=fetcher.pode_acessar)
    finally:
        contexto.close()


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
