"""VERIFICAÇÃO: a fixture `contexto_gui` isola de verdade (R20).

O risco que este arquivo cobre não é a fixture estourar — é ela **funcionar** e,
de quebra, mudar o viewport da página de sessão. `browser_page` é a mesma página
que `checks/frontend/test_rendering.py` usa para medir FCP, LCP e CLS; um check
de GUI que a redimensionasse deixaria as Web Vitals das outras dimensões medidas
num viewport que ninguém declarou, e o número sairia errado sem nada ficar
vermelho.

Duas provas, e a segunda existe porque a primeira sozinha é fraca:

1. **comportamental** — dois contextos reais no mesmo navegador; mexer num não
   move o outro. Sem rede: `about:blank` basta para ler `viewport_size`;
2. **no fonte** — a fixture do `conftest.py` não menciona `browser_page`. É a
   guarda que continua valendo quando alguém escrever a fixture de novo daqui a
   um ano, e que a prova comportamental não daria, porque ela exercita o
   caminho de hoje.
"""
import ast
from pathlib import Path

import pytest

from webqa.viewports import Viewport, opcoes_de_contexto

pytestmark = [pytest.mark.verification, pytest.mark.browser]

RAIZ = Path(__file__).resolve().parent.parent
CONFTEST = RAIZ / "conftest.py"

_MOBILE = Viewport("mobile", 390, 844, mobile=True, toque=True)


@pytest.fixture(scope="module")
def navegador():
    """Chromium cru, sem alvo: estes testes provam isolamento de contexto, não
    comportamento contra um site. Sem rede, portanto sem a regra da casa de
    `tests/` ser livre de rede em risco."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")
    with sync_playwright() as p:
        try:
            instancia = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium indisponível: rode `python -m playwright install "
                        f"chromium` ({exc}).")
        yield instancia
        instancia.close()


def test_contexto_novo_nao_move_a_pagina_de_sessao(navegador):
    """A prova que dá nome ao arquivo: a página de sessão sai como entrou.

    `pagina_de_sessao` é o análogo de `browser_page` — mesma construção
    (`new_page` sem viewport), mesmo papel. Ler o viewport dela DEPOIS de usar o
    contexto de GUI é o que separa "isolou" de "não estourou".
    """
    pagina_de_sessao = navegador.new_page()
    antes = pagina_de_sessao.viewport_size

    contexto = navegador.new_context(**opcoes_de_contexto(_MOBILE))
    try:
        pagina_gui = contexto.new_page()
        assert pagina_gui.viewport_size == {"width": 390, "height": 844}
    finally:
        contexto.close()

    assert pagina_de_sessao.viewport_size == antes, (
        "a página de sessão mudou de viewport — as Web Vitals de frontend "
        "passariam a ser medidas num tamanho que ninguém declarou (R20)")
    pagina_de_sessao.close()


def test_contextos_de_gui_nao_se_contaminam(navegador):
    """Duas variações simultâneas continuam sendo duas — o segundo contexto não
    herda o viewport do primeiro, que é o que aconteceria com página compartilhada."""
    a = navegador.new_context(**opcoes_de_contexto(_MOBILE))
    b = navegador.new_context(**opcoes_de_contexto(Viewport("desktop", 1366, 768)))
    try:
        assert a.new_page().viewport_size == {"width": 390, "height": 844}
        assert b.new_page().viewport_size == {"width": 1366, "height": 768}
    finally:
        a.close()
        b.close()


def test_preferencia_de_tema_fica_no_contexto(navegador):
    """`color_scheme` é a outra variação que contaminaria a sessão inteira se
    fosse aplicada na página compartilhada."""
    contexto = navegador.new_context(**opcoes_de_contexto(None, color_scheme="dark"))
    try:
        pagina = contexto.new_page()
        escuro = pagina.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches")
        assert escuro is True
    finally:
        contexto.close()

    padrao = navegador.new_page()
    assert padrao.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches") is False
    padrao.close()


# ---------- Guarda no fonte ----------

def _corpo_de(nome: str) -> str:
    """Corpo da função `nome` no conftest, lido por AST — não por recorte de
    texto, que casaria com o nome citado numa docstring vizinha."""
    arvore = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            corpo = [f for f in no.body if not isinstance(f, ast.Expr)
                     or not isinstance(f.value, ast.Constant)]
            return "\n".join(ast.unparse(f) for f in corpo)
    raise AssertionError(f"função {nome!r} não existe mais em conftest.py")


# As duas fixtures de contexto de GUI e a implementação que ambas delegam. A
# lista é EXPLÍCITA: extraí-la do conftest faria a cobertura encolher junto com
# uma fixture nova que alguém acrescentasse sem pensar na guarda.
FIXTURES_DE_CONTEXTO = ("contexto_gui", "contexto_gui_modulo")
IMPLEMENTACAO = "_contextos_de_gui"


@pytest.mark.parametrize("nome", [*FIXTURES_DE_CONTEXTO, IMPLEMENTACAO])
def test_contexto_de_gui_nao_conhece_browser_page(nome):
    """Fronteira no fonte: nada disso pode sequer mencionar a página de sessão.

    Mais forte que a prova comportamental acima, e por um motivo específico: ela
    continua valendo para a PRÓXIMA versão da fixture. Um teste que só exercita
    o caminho de hoje não impede alguém de reintroduzir o acoplamento amanhã.
    """
    assert "browser_page" not in _corpo_de(nome), (
        f"{nome} menciona browser_page — a página de sessão é compartilhada "
        "com checks/frontend/test_rendering.py e não pode ser tocada (R20)")


def test_implementacao_fecha_o_que_abriu():
    """Contexto vazando entre testes é estado herdado com outro nome."""
    corpo = _corpo_de(IMPLEMENTACAO)
    assert "finally" in corpo and ".close()" in corpo, (
        f"{IMPLEMENTACAO} precisa fechar os contextos num finally: teste que "
        "estoura no meio não pode deixar navegador aberto para o resto da sessão")


def test_implementacao_e_casca_fina_sobre_a_biblioteca():
    """`checks/` só conhece fixtures; o detalhe vive em `webqa/`
    (docs/ARQUITETURA.md). A tradução do perfil é delegada, não repetida."""
    corpo = _corpo_de(IMPLEMENTACAO)
    assert "opcoes_de_contexto" in corpo
    assert "is_mobile" not in corpo, "a tradução do perfil pertence a webqa/viewports.py"


@pytest.mark.parametrize("nome", FIXTURES_DE_CONTEXTO)
def test_as_duas_fixtures_delegam_a_mesma_implementacao(nome):
    """Uma implementação, dois escopos.

    Duas cópias do corpo divergiriam no primeiro campo novo — e a divergência
    apareceria como um check isolando o contexto e o outro não, que é
    exatamente o defeito silencioso que a fixture existe para impedir.
    """
    corpo = _corpo_de(nome)
    assert IMPLEMENTACAO in corpo, f"{nome} não delega a {IMPLEMENTACAO}"
    assert "new_context" not in corpo, f"{nome} tem cópia própria da implementação"


def test_escopos_das_duas_fixtures():
    """A de módulo existe para a observação CARA e partilhada — a caminhada de
    foco alimenta três critérios e percorrer a página três vezes pagaria três
    vezes pela mesma observação. Trocar os escopos sem perceber desfaria isso."""
    arvore = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    escopos = {}
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef) and no.name in FIXTURES_DE_CONTEXTO:
            escopos[no.name] = {ast.unparse(d) for d in no.decorator_list}
    assert "pytest.fixture()" in escopos["contexto_gui"]
    assert "pytest.fixture(scope='module')" in escopos["contexto_gui_modulo"]
