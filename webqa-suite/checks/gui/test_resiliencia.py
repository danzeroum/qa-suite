"""A API falhou. E agora, o que o visitante vê?

Nielsen **H9** (reconhecer, diagnosticar e recuperar-se de erros) e **H1**
(visibilidade do estado); ISO 25010, tolerância a falhas. Tela branca sob 500 é o
pior defeito de interface que existe, e nada na suíte o pegava.

**Quatro modos de falha, quatro checks, nunca parametrizados.** O contrato do
alvo fixture é por nodeid exato (`fixture_target/esperado.json`, §2.8), e
`::test_x[500]` não é um nodeid que sobreviva a alguém reordenar a lista. Além
disso os quatro terminam em desfechos DIFERENTES contra o mesmo alvo, e um
parametrize os apresentaria como quatro amostras da mesma pergunta.

**A fronteira, escrita porque "simular 500" soa a sondagem ativa e não é.** A
interceptação acontece no CLIENTE (`page.route`): o alvo recebe *menos*
requisições, nunca mais, e nunca uma que ele não tenha oferecido. Passivo pelo
critério de `docs/GUI.md §2.1`, sem gate. E só endpoint de MESMA ORIGEM é
interceptado — terceiro nunca.

**Evidência é texto, nunca pixel.** Esta é a spec de maior risco de PII do
conjunto: tela de erro de aplicação real costuma exibir dado de quem estava
logado. O achado se sustenta inteiro em seletor e texto sanitizado — não há
captura, e por isso não há o que vazar.
"""
import pytest

from webqa import metricas
from webqa.auth import origem_de
from webqa.degradacao import (
    Laudo,
    avaliar,
    carregar_vocabulario,
    endpoints_de_mesma_origem,
    excedeu_tentativas,
)

pytestmark = [pytest.mark.gui, pytest.mark.browser]

# Janela de observação depois da falha. Generosa de propósito: SPA com repetição
# de recuo exponencial precisa de tempo para desistir e mostrar o que mostra, e
# medir antes disso acusaria de silêncio uma página que ainda estava tentando.
_JANELA_MS = 5_000

# Folga depois do `networkidle`, antes de derrubar a conexão. Ver `_assentar`.
_ASSENTAMENTO_MS = 500

# Corpo de 500 do mundo real: proxy e servidor devolvem HTML mesmo em rota de
# API. É a causa número um de "Unexpected token '<'" — e é o que faz a diferença
# entre um alvo que trata a falha e um que despeja o erro cru na tela.
_CORPO_500 = ("<!doctype html><html><head><title>500 Internal Server Error</title>"
              "</head><body><h1>500 Internal Server Error</h1></body></html>")

# Resposta cortada no meio: conexão interrompida, proxy com buffer estourado,
# resposta truncada por limite de tamanho. Válida como bytes, inválida como JSON.
_JSON_TRUNCADO = '{"total": 3, "ite'


class _Observacao:
    """A carga saudável — a régua contra a qual a degradação é lida."""

    def __init__(self, dom: str, endpoints: tuple[str, ...], erros_console: int):
        self.dom = dom
        self.endpoints = endpoints
        self.erros_console = erros_console


@pytest.fixture(scope="module")
def vocabulario():
    return carregar_vocabulario()


@pytest.fixture(scope="module")
def carga_saudavel(contexto_gui_modulo, settings, perfis_gui) -> _Observacao:
    """Carrega o alvo UMA vez, sem interceptar nada, e guarda o que ele pediu.

    Descoberta passiva dos endpoints: são os endereços que a própria página
    buscou. Nada é adivinhado nem enumerado — a doutrina de
    `webqa/navegacao.py::percorrer`, onde página que ninguém linkou não existe.

    Serve também de LINHA DE BASE para duas coisas que sem ela seriam ruído: o
    texto que já estava na tela antes da falha (senão um rodapé com a palavra
    "erro" passaria por resposta à falha) e os erros de console que o alvo já
    produzia (o fixture produz três numa carga saudável, e cobrá-los aqui seria
    cobrar deste check o defeito de outro).
    """
    pagina = contexto_gui_modulo(viewport=perfis_gui["desktop"])
    requisicoes, erros = [], []
    pagina.on("request", lambda r: requisicoes.append((r.url, r.resource_type)))
    _escutar_erros(pagina, erros)
    pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
    pagina.wait_for_timeout(_JANELA_MS)
    return _Observacao(
        dom=pagina.content(),
        # ORIGEM, não `target_url`: o alvo pode ser uma página interna
        # (`.../gui/resiliente`) enquanto a API vive em `.../gui/api/pedidos`.
        # Comparar com a URL inteira descartaria como "terceiro" um endpoint do
        # próprio alvo — e o check pularia dizendo que não há o que interceptar.
        endpoints=endpoints_de_mesma_origem(requisicoes, origem_de(settings.target_url)),
        erros_console=len(erros),
    )


def _escutar_erros(pagina, destino: list) -> None:
    pagina.on("console", lambda m: destino.append(m.text) if m.type == "error" else None)
    pagina.on("pageerror", lambda e: destino.append(str(e)))


def _degradar(contexto_gui, settings, saudavel, vocabulario, manipulador=None,
              offline: bool = False):
    """Carrega o alvo com a falha injetada e devolve (laudo, tentativas, erros novos).

    Uma implementação só para os quatro modos: o que muda entre eles é o
    manipulador de rota, e duplicar o corpo faria os quatro divergirem no
    primeiro campo novo — com a divergência aparecendo como um modo medindo algo
    que o outro não mede.
    """
    pagina = contexto_gui(viewport=None)
    tentativas, erros = [], []
    alvos = set(saudavel.endpoints)
    pagina.on("request", lambda r: tentativas.append(r.url) if r.url in alvos else None)
    _escutar_erros(pagina, erros)

    if manipulador is not None:
        for endereco in saudavel.endpoints:
            pagina.route(endereco, manipulador)
    try:
        pagina.goto(settings.target_url, wait_until="load", timeout=60_000)
        if offline:
            _assentar(pagina)
            # DEPOIS da carga ASSENTADA: o cenário é a conexão caindo com a
            # página aberta, não a página nascendo offline. O navegador dispara o
            # evento `offline` no `window` — quem escuta consegue avisar, quem
            # não escuta não tem como.
            pagina.context.set_offline(True)
        pagina.wait_for_timeout(_JANELA_MS)
        laudo = avaliar(pagina.content(), saudavel.dom, vocabulario=vocabulario)
    finally:
        # Rota pendente (o modo "não responde") deixaria o fechamento do contexto
        # cancelar um handler no meio e poluir a saída com traceback do asyncio.
        pagina.unroute_all(behavior="ignoreErrors")
    return laudo, len(tentativas), max(0, len(erros) - saudavel.erros_console)


def _assentar(pagina) -> None:
    """Espera a carga inicial TERMINAR antes de derrubar a conexão.

    Medido, não suposto: cortar a rede no instante do `load` produzia um
    resultado invertido. O evento `offline` disparava, a página conforme mostrava
    o aviso — e então o `fetch` que já estava no ar resolvia com sucesso e
    SOBRESCREVIA o aviso com o conteúdo normal. O check acusava de silêncio uma
    página que tinha avisado, e a acusação era do próprio check.

    A raiz é de cenário, não de corrida: "a conexão caiu com a página aberta" e
    "a conexão caiu no meio da carga" são situações diferentes, e a segunda tem
    outro nome. Este check mede a primeira.
    """
    try:
        pagina.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass          # alvo com conexão longa (SSE, websocket) nunca fica ocioso
    pagina.wait_for_timeout(_ASSENTAMENTO_MS)


def _exigir_endpoints(saudavel) -> None:
    if not saudavel.endpoints:
        pytest.skip(
            "Alvo sem chamada XHR/fetch de MESMA ORIGEM observável na carga — não há "
            "o que interceptar, e interceptar terceiro está fora do escopo por regra. "
            "Ausência de endpoint não é resiliência comprovada: é ausência de medida.")


def _julgar(laudo: Laudo, tentativas: int, erros_novos: int, settings, *, modo: str,
            endpoints) -> None:
    """Os três desfechos, nesta ordem — e a ordem é o argumento.

    Tela branca e termo vazado vêm primeiro porque são inequívocos. A ausência de
    mensagem vem por ÚLTIMO, e só quando não há nada mais grave a dizer: um alvo
    que mostra `SyntaxError` na tela não pode sair do laudo como "não reconheci a
    mensagem". Mesma lição da OS-46, onde o estouro de orçamento precede a
    ausência de INP.
    """
    onde = f"Endpoint(s) interceptado(s): {', '.join(endpoints)}."
    metricas.registrar("gui_resil_tentativas_n", tentativas)
    metricas.registrar("gui_resil_console_erros_n", erros_novos)

    assert not laudo.tela_branca, (
        f"{modo}: a página ficou SEM conteúdo principal — o visitante vê tela branca e "
        f"não sabe o que aconteceu (Nielsen H9). {onde}")
    assert not laudo.termos_vazados, (
        f"{modo}: a tela expõe detalhe técnico ao visitante — {list(laudo.termos_vazados)}. "
        f"Isso é a mensagem do programador vazando para quem está comprando, e costuma "
        f"vir acompanhada de dado interno. {onde}\nTexto novo na tela:\n{laudo.trecho}")
    assert not excedeu_tentativas(tentativas, settings.threshold("gui_resil_tentativas_max")), (
        f"{modo}: {tentativas} requisições ao(s) endpoint(s) na janela de "
        f"{_JANELA_MS}ms (teto {settings.threshold('gui_resil_tentativas_max'):.0f}) — "
        f"a página está martelando um serviço que já respondeu que está fora. {onde}")
    assert erros_novos <= settings.threshold("gui_console_erros_pos_falha_max"), (
        f"{modo}: {erros_novos} erros NOVOS no console em relação à carga saudável "
        f"(teto {settings.threshold('gui_console_erros_pos_falha_max'):.0f}). {onde}")

    if not laudo.mensagem_visivel:
        pytest.xfail(
            f"{modo}: nenhuma mensagem de erro reconhecível apareceu na tela. "
            "SINAL, não prova — a heurística é um vocabulário de palavras, e "
            "vocabulário não cobre alvo internacionalizado; reprovar com heurística "
            f"fraca custaria a credibilidade da bateria inteira. {onde}\n"
            f"Texto novo na tela após a falha:\n{laudo.trecho or '  (nenhum)'}")


def test_erro_500_na_api_nao_vaza_detalhe_tecnico(contexto_gui, settings, carga_saudavel,
                                                  vocabulario):
    """GUI-RESIL-01: a API responde 500 com a página de erro do servidor."""
    _exigir_endpoints(carga_saudavel)

    def responder_500(rota):
        rota.fulfill(status=500, content_type="text/html; charset=utf-8", body=_CORPO_500)

    laudo, tentativas, erros = _degradar(contexto_gui, settings, carga_saudavel,
                                         vocabulario, responder_500)
    _julgar(laudo, tentativas, erros, settings, modo="Com a API respondendo 500",
            endpoints=carga_saudavel.endpoints)


def test_api_que_nao_responde_avisa_o_visitante(contexto_gui, settings, carga_saudavel,
                                                vocabulario):
    """GUI-RESIL-02: o pedido fica pendente pela janela inteira.

    O modo é "não responde", e não "recusa": a rota é interceptada e NUNCA
    resolvida. Abortar produziria uma rejeição imediata, que é erro de rede — e
    erro de rede é um caminho de código que muitas páginas tratam. O que este
    check mede é o outro: o spinner que gira para sempre porque ninguém pôs
    prazo no pedido.
    """
    _exigir_endpoints(carga_saudavel)

    def nunca_responder(rota):
        pass                  # sem fulfill, sem abort: o pedido fica pendente

    laudo, tentativas, erros = _degradar(contexto_gui, settings, carga_saudavel,
                                         vocabulario, nunca_responder)
    _julgar(laudo, tentativas, erros, settings, modo="Com a API sem responder",
            endpoints=carga_saudavel.endpoints)


def test_json_truncado_nao_vaza_detalhe_tecnico(contexto_gui, settings, carga_saudavel,
                                                vocabulario):
    """GUI-RESIL-03: a resposta chega com 200 e cortada no meio.

    É o modo mais traiçoeiro dos três: o status diz sucesso, o corpo é bytes
    válidos, e a falha só aparece no `JSON.parse`. Código que confere `r.ok` e
    para por aí passa direto por aqui.
    """
    _exigir_endpoints(carga_saudavel)

    def responder_truncado(rota):
        rota.fulfill(status=200, content_type="application/json", body=_JSON_TRUNCADO)

    laudo, tentativas, erros = _degradar(contexto_gui, settings, carga_saudavel,
                                         vocabulario, responder_truncado)
    _julgar(laudo, tentativas, erros, settings, modo="Com a API devolvendo JSON truncado",
            endpoints=carga_saudavel.endpoints)


def test_perda_de_conexao_e_comunicada(contexto_gui, settings, carga_saudavel, vocabulario):
    """GUI-RESIL-04: a conexão cai com a página já aberta (Nielsen H1).

    Nada é interceptado aqui — o contexto vai a offline depois da carga, e o
    navegador dispara o evento `offline` no `window`. A pergunta é se a página
    escuta. Quem não escuta não tem como avisar, e o visitante descobre que está
    sem rede quando o próximo clique não faz nada.
    """
    laudo, tentativas, erros = _degradar(contexto_gui, settings, carga_saudavel,
                                         vocabulario, offline=True)
    _julgar(laudo, tentativas, erros, settings, modo="Com a conexão perdida após a carga",
            endpoints=carga_saudavel.endpoints or ("nenhum — só o evento offline",))
