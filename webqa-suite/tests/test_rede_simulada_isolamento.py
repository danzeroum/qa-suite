"""VERIFICAÇÃO: o estrangulamento morre com o contexto que o abriu (OS-50).

É o R20 em versão rede, e o risco não é o teste estourar — é ele **funcionar** e,
de quebra, deixar a CPU emulada ligada para o resto da sessão. `browser_page` é a
página que `checks/frontend/test_rendering.py` usa para medir FCP, LCP e CLS: um
check de GUI que a estrangulasse faria as Web Vitals das outras dimensões serem
medidas sob 3G sem ninguém declarar isso. O LCP sairia péssimo, o alvo estaria
intacto, e nada ficaria vermelho — que é o pior formato de número errado.

**Por que a prova é de CPU e não de rede.** O fator de throttling de CPU é
observável sem baixar um único byte: um laço computacional de tamanho fixo em
`about:blank` demora ×4 sob emulação. Isso mantém `tests/` livre de rede (mesma
construção de `tests/test_gui_fixtures.py`) e ainda assim exercita o mecanismo
real — a sessão CDP é a mesma que carrega as duas emulações, então provar que a
de CPU não vaza é provar que a sessão não vaza.

O não-vazamento de REDE foi medido contra o alvo fabricado e registrado no PR da
OS-50: a mesma página que mede 3376ms de LCP sob o perfil mede 68ms num contexto
novo aberto depois.
"""
import pytest

from webqa.rede_simulada import PerfilDeRede, estrangular

pytestmark = [pytest.mark.verification, pytest.mark.browser]

# Laço de tamanho FIXO: o que muda entre os contextos é a velocidade da máquina
# emulada, nunca a quantidade de trabalho. Um laço com prazo de relógio
# (`while Date.now() < fim`) não serviria — ele é imune a throttling de CPU, que
# foi exatamente a descoberta que obrigou a OS-50 a criar `/gui/pesado` em vez de
# reusar o bloqueio da home.
_LACO = """
() => {
  const t = performance.now();
  let s = 0;
  for (let i = 0; i < 3000000; i++) { s += Math.sqrt(i) * Math.sin(i); }
  window.__s = s;
  return performance.now() - t;
}
"""

_FATOR = 4
_PERFIL = PerfilDeRede(nome="teste", download_kbps=1638.4, upload_kbps=750,
                       latencia_ms=150, cpu_fator=_FATOR)

# Margem larga de propósito: o fator nominal é 4 e a asserção cobra só 2. O que
# está sendo provado é "estrangulou aqui e não ali", não a exatidão do fator —
# cobrar 4 com precisão transformaria variação normal de máquina compartilhada em
# vermelho, e um teste que oscila é pior que um teste ausente.
_FATOR_MINIMO_OBSERVAVEL = 2


@pytest.fixture(scope="module")
def navegador():
    """Chromium cru, sem alvo — estes testes provam isolamento, não comportamento
    contra um site."""
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


def _tempo_do_laco(navegador, estrangulado: bool) -> float:
    contexto = navegador.new_context()
    pagina = contexto.new_page()
    try:
        if estrangulado:
            estrangular(pagina, _PERFIL)
        pagina.goto("about:blank")
        return float(pagina.evaluate(_LACO))
    finally:
        contexto.close()


def test_o_estrangulamento_de_cpu_realmente_acontece(navegador):
    """A metade que quase ninguém escreve, e sem a qual a outra não vale nada.

    Um `estrangular` que não fizesse nada passaria no teste de não-vazamento
    abaixo com louvor — nada vaza quando nada acontece. As duas asserções são
    uma prova só, e é por isso que moram no mesmo arquivo.
    """
    livre = _tempo_do_laco(navegador, estrangulado=False)
    preso = _tempo_do_laco(navegador, estrangulado=True)
    assert preso > livre * _FATOR_MINIMO_OBSERVAVEL, (
        f"o laço levou {preso:.0f}ms sob CPU ×{_FATOR} contra {livre:.0f}ms livre — "
        "a emulação não teve efeito observável, e um check apoiado nela mediria "
        "fibra com nome de 3G")


def test_contexto_novo_nasce_livre_do_estrangulamento_do_vizinho(navegador):
    """O R20 em versão rede: contexto estrangulado não contamina o seguinte."""
    preso = _tempo_do_laco(navegador, estrangulado=True)
    depois = _tempo_do_laco(navegador, estrangulado=False)
    assert preso > depois * _FATOR_MINIMO_OBSERVAVEL, (
        f"contexto aberto DEPOIS do estrangulado levou {depois:.0f}ms contra "
        f"{preso:.0f}ms — a emulação vazou do contexto que a declarou, e qualquer "
        "medida seguinte da sessão está sob uma condição que ninguém declarou")
