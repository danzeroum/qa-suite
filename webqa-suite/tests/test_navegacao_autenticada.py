"""VERIFICAÇÃO: exploração passiva autenticada (OS-38) — a disciplina do crawl.

O que se prova aqui não é "o crawler acha páginas". É que ele acha **apenas** as
que a aplicação oferece — e a prova é a página órfã: ela existe, responde 200, e
nunca é visitada. Um crawler que a alcançasse teria fabricado o endereço, e
fabricar endereço é Fase C, que continua desligada.

Três camadas, e a ordem importa:

1. a guarda de AST, provada contra violação plantada antes de ser usada;
2. a disciplina do percurso (proveniência, órfã, etiqueta), sem rede;
3. a regressão do achado da OS-37 — `robots.txt` de alvo protegido — que só
   apareceu contra host real e por isso vira teste permanente.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from webqa import navegacao
from webqa.etiqueta import PoliteFetcher
from webqa.navegacao import ENTRADA, Pagina, links_oferecidos, percorrer, proveniencias

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
FONTE_DO_CRAWLER = RAIZ / "webqa" / "navegacao.py"


# ---------- 1. A guarda de AST: nenhuma URL nasce no fonte ----------

def _docstrings(arvore: ast.AST) -> set[int]:
    """`id()` dos nós que são docstring — texto que explica não é código que age."""
    ignorar = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        corpo = getattr(no, "body", [])
        if (corpo and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)):
            ignorar.add(id(corpo[0].value))
    return ignorar


def geracao_de_url_em(fonte: str, arquivo: str = "<memória>") -> list[str]:
    """Endereços nascendo no FONTE. Vazio = o crawler só segue dado.

    Dois padrões, porque são as duas formas de adivinhar:

    * **literal de caminho** (`"/admin"`, `"/.git/HEAD"`) — nomear rota no código
      é dizer ao programa onde ir sem que a aplicação tenha oferecido. `"/"`
      sozinho é permitido: normaliza base, não nomeia destino;
    * **`urljoin` com destino constante** — a junção tem de receber os dois lados
      de dados. Se o segundo lado é literal, o endereço foi fabricado.

    Pública de propósito: o teste do próprio detector a chama com fonte
    fabricado, como em `test_fase_c_travada.py`.
    """
    arvore = ast.parse(fonte)
    ignorar = _docstrings(arvore)
    achados: list[str] = []

    for no in ast.walk(arvore):
        if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                and id(no) not in ignorar
                and no.value.startswith("/") and len(no.value) > 1):
            achados.append(f"{arquivo}:{no.lineno} → literal de caminho {no.value[:40]!r}")
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "urljoin" and len(no.args) >= 2
                and isinstance(no.args[1], ast.Constant)):
            achados.append(f"{arquivo}:{no.lineno} → urljoin com destino constante")

    return achados


def test_o_detector_pega_geracao_de_url_plantada():
    """Detector que nunca detectou violação plantada não está provado."""
    plantado = 'from urllib.parse import urljoin\ndef ir(base):\n    return urljoin(base, "/admin")\n'
    achados = geracao_de_url_em(plantado, "plantado.py")
    assert len(achados) == 2, achados
    assert any("literal de caminho" in a for a in achados)
    assert any("urljoin com destino constante" in a for a in achados)


def test_o_detector_nao_acusa_juncao_legitima():
    """`urljoin(url_da_pagina, href)` com os dois lados vindos de dado é o certo."""
    limpo = 'from urllib.parse import urljoin\ndef ir(pagina, href):\n    return urljoin(pagina, href)\n'
    assert geracao_de_url_em(limpo) == []


def test_o_crawler_nao_fabrica_nenhum_endereco():
    """A fronteira entre passivo-autenticado e Fase C, como invariante estrutural."""
    achados = geracao_de_url_em(FONTE_DO_CRAWLER.read_text(encoding="utf-8"), "webqa/navegacao.py")
    assert achados == [], (
        "o crawler autenticado passou a fabricar endereço — isso é Fase C vazando:\n"
        + "\n".join(achados))


def test_o_crawler_nao_menciona_caminho_sensivel():
    """Reusa o detector da OS-36: a fronteira é a mesma, e o dono dela também."""
    from tests.test_fase_c_travada import sondagens_em

    achados = sondagens_em(FONTE_DO_CRAWLER.read_text(encoding="utf-8"), "webqa/navegacao.py")
    assert achados == [], "\n".join(achados)


# ---------- 2. A disciplina do percurso ----------

MENU = ('<nav><a href="/produtos">P</a><a href="/conta">C</a></nav>')


def _app(paginas: dict[str, str]):
    """Aplicação fabricada: devolve `abrir(url)` e o registro do que foi pedido."""
    pedidos: list[str] = []

    def abrir(url):
        pedidos.append(url)
        caminho = url.split("://", 1)[1].split("/", 1)
        rota = "/" + (caminho[1] if len(caminho) > 1 else "")
        if rota not in paginas:
            return 404, ""
        return 200, paginas[rota]

    return abrir, pedidos


def test_visita_as_paginas_ligadas_pelo_menu():
    abrir, pedidos = _app({
        "/": MENU, "/produtos": MENU, "/conta": MENU, "/orfa": "<p>sozinha</p>",
    })
    visitadas = percorrer("http://alvo.test/", abrir)
    urls = {p.url for p in visitadas}
    assert "http://alvo.test/produtos" in urls
    assert "http://alvo.test/conta" in urls


def test_pagina_orfa_nunca_e_visitada():
    """O coração do aceite: ela EXISTE e responde 200 — e mesmo assim não é vista.

    Se este teste falhar, alguém ensinou o crawler a adivinhar endereço.
    """
    abrir, pedidos = _app({
        "/": MENU, "/produtos": MENU, "/conta": MENU, "/orfa": "<p>sozinha</p>",
    })
    visitadas = percorrer("http://alvo.test/", abrir)
    assert "http://alvo.test/orfa" not in {p.url for p in visitadas}
    assert not any("orfa" in u for u in pedidos), "a órfã chegou a ser REQUISITADA"


def test_toda_url_visitada_tem_proveniencia():
    abrir, _ = _app({"/": MENU, "/produtos": MENU, "/conta": MENU})
    visitadas = percorrer("http://alvo.test/", abrir)
    origens = proveniencias(visitadas)
    assert origens["http://alvo.test/"] == ENTRADA
    for url, origem in origens.items():
        if url != "http://alvo.test/":
            assert origem.startswith("link em "), f"{url} sem proveniência de link"


def test_nenhuma_url_e_adivinhada():
    """Toda página visitada, menos a entrada, veio de um link de outra visitada."""
    abrir, _ = _app({"/": MENU, "/produtos": MENU, "/conta": MENU})
    visitadas = percorrer("http://alvo.test/", abrir)
    conhecidas = {p.url for p in visitadas}
    for p in visitadas:
        if p.veio_de_link:
            assert p.origem.removeprefix("link em ") in conhecidas


def test_respeita_a_etiqueta_mesmo_com_link_oferecido():
    """Oferecer não revoga ter pedido para não entrar."""
    abrir, pedidos = _app({"/": MENU, "/produtos": MENU, "/conta": MENU})
    visitadas = percorrer("http://alvo.test/", abrir,
                          pode_acessar=lambda u: "produtos" not in u)
    assert "http://alvo.test/produtos" not in {p.url for p in visitadas}
    assert not any("produtos" in u for u in pedidos)


def test_teto_de_paginas_e_respeitado():
    abrir, _ = _app({"/": MENU, "/produtos": MENU, "/conta": MENU})
    assert len(percorrer("http://alvo.test/", abrir, teto=2)) == 2


def test_nao_sai_do_host_do_alvo():
    abrir, pedidos = _app({"/": '<a href="https://outro.test/x">fora</a>'})
    percorrer("http://alvo.test/", abrir)
    assert not any("outro.test" in u for u in pedidos)


def test_ignora_esquemas_que_nao_sao_navegacao():
    html = '<a href="mailto:a@b.com">m</a><a href="tel:+551199">t</a><a href="#topo">a</a>'
    assert links_oferecidos(html, "http://alvo.test/", "alvo.test") == []


def test_pagina_que_nao_abre_nao_derruba_o_percurso():
    def abrir(url):
        if "conta" in url:
            raise RuntimeError("timeout")
        return 200, MENU

    visitadas = percorrer("http://alvo.test/", abrir)
    assert {p.url for p in visitadas} == {"http://alvo.test/", "http://alvo.test/produtos"}


def test_formulario_nao_e_seguido():
    """Submeter escreve no sistema do alvo — é interação, e mora atrás do gate."""
    html = '<form action="/comprar" method="post"><button>ok</button></form>'
    assert links_oferecidos(html, "http://alvo.test/", "alvo.test") == []


# ---------- 3. Regressão do achado da OS-37: robots.txt de alvo protegido ----------

class _Resposta:
    def __init__(self, status, texto=""):
        self.status_code = status
        self.text = texto


class _CredencialFake:
    cabecalho_basic = "Basic Zm9vOmJhcg=="


def _fetcher_espiao(status_por_url, credencial=None, origem=""):
    """Devolve `(fetcher, cabecalhos_vistos)` — permite inspecionar o Authorization."""
    vistos: list[tuple[str, dict]] = []

    def get(url, timeout=None, headers=None):
        vistos.append((url, dict(headers or {})))
        return _Resposta(*status_por_url(url))

    return PoliteFetcher("WebQA/teste", get=get, credencial=credencial,
                         origem_do_alvo=origem), vistos


def test_robots_de_alvo_protegido_sem_credencial_pula_com_motivo():
    """A REGRESSÃO do achado: sem credencial, a dimensão functional nascia cega.

    Verificado contra host real na OS-37 (`robots.txt respondeu HTTP 401 — alvo
    pulado`). Vira teste permanente para que o conserto não seja desfeito sem
    alguém dizer que está desfazendo.
    """
    fetcher, _ = _fetcher_espiao(lambda u: (401,))
    veredito = fetcher.preparar("https://alvo.test/")
    assert veredito.bloqueado
    assert "sem credencial" in veredito.motivo
    assert "WEBQA_BASIC_AUTH" in veredito.motivo, "a mensagem tem de dizer o que fazer"


def test_robots_de_alvo_protegido_com_credencial_e_lido():
    """Com credencial e 2xx, a política é lida e a dimensão volta a ter veredito."""
    fetcher, vistos = _fetcher_espiao(
        lambda u: (200, "User-agent: *\nDisallow: /privado\n"),
        credencial=_CredencialFake(), origem="https://alvo.test")
    veredito = fetcher.preparar("https://alvo.test/")
    assert veredito.permitido, veredito.motivo
    assert fetcher.pode_acessar("https://alvo.test/publico")
    assert not fetcher.pode_acessar("https://alvo.test/privado")
    assert "Authorization" in vistos[0][1]


def test_credencial_recusada_no_robots_bloqueia_dizendo_que_era_com_credencial():
    """Credencial errada é DADO, não licença para ignorar a política."""
    fetcher, _ = _fetcher_espiao(lambda u: (401,), credencial=_CredencialFake(),
                                 origem="https://alvo.test")
    veredito = fetcher.preparar("https://alvo.test/")
    assert veredito.bloqueado
    assert "MESMO com credencial" in veredito.motivo


def test_robots_de_terceiro_e_consultado_anonimo():
    """A barreira da OS-37 estendida à cortesia: terceiro nunca vê a credencial."""
    fetcher, vistos = _fetcher_espiao(lambda u: (200, ""), credencial=_CredencialFake(),
                                      origem="https://alvo.test")
    fetcher.preparar("https://cdn.terceiro.test/")
    url, headers = vistos[0]
    assert "cdn.terceiro.test" in url
    assert "Authorization" not in headers, "a credencial do alvo vazou para terceiro"


def test_credencial_nao_vai_em_http_puro_nem_para_o_alvo():
    """Mesma regra de esquema da OS-37 — robots em claro não leva senha."""
    fetcher, vistos = _fetcher_espiao(lambda u: (200, ""), credencial=_CredencialFake(),
                                      origem="http://alvo.test")
    fetcher.preparar("http://alvo.test/")
    assert "Authorization" not in vistos[0][1]


def test_sem_credencial_o_comportamento_e_o_de_antes():
    """Alvo anônimo não muda de comportamento por causa de recurso que não usa."""
    fetcher, vistos = _fetcher_espiao(lambda u: (200, ""))
    fetcher.preparar("https://alvo.test/")
    assert set(vistos[0][1]) == {"User-Agent"}


# ---------- Contrato do alvo fixture autenticado ----------

def test_o_alvo_fixture_tem_uma_orfa_de_verdade():
    """A topologia é o fixture: se a órfã for linkada, o aceite perde o sentido."""
    from fixture_target.autenticado import PAGINAS

    todas = b" ".join(PAGINAS.values()).decode("utf-8")
    assert "/orfa" in PAGINAS or "orfa" in str(PAGINAS.keys())
    assert 'href="/orfa"' not in todas, "a órfã foi linkada — deixou de ser órfã"


def test_o_alvo_fixture_serve_cookie_de_sessao_auditavel():
    from fixture_target.autenticado import COOKIE_DE_SESSAO

    assert "HttpOnly" in COOKIE_DE_SESSAO and "SameSite" in COOKIE_DE_SESSAO


def test_pagina_carrega_html_e_status():
    p = Pagina(url="http://a/", origem=ENTRADA, status=200, html="<p>x</p>")
    assert not p.veio_de_link
    assert navegacao.ENTRADA == ENTRADA
