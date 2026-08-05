"""VERIFICAÇÃO: as exceções da WCAG 2.5.8 e o inventário de zoom.

Este arquivo existe por um motivo específico: **um check ingênuo de tamanho de
alvo reprova em massa.** Todo site com link dentro de parágrafo tem dezenas de
alvos abaixo de 24px que a norma perdoa. Um detector que os acusasse produziria
um laudo que ninguém lê depois da segunda vez — e a dimensão inteira perderia a
credibilidade, que é o mesmo argumento com que `webqa/sanitize.py` recusa
detecção por entropia.

Por isso os casos de borda vêm primeiro: encostar não é intersectar, e
insuficiente por 1px é insuficiente.
"""
import pytest

from webqa.geometria import (
    Caixa,
    classificar_alvos,
    excecao_de,
    perdidos_entre,
    resumo_de_caixas,
    resumo_de_isentos,
)

pytestmark = pytest.mark.verification

MIN = 24.0
META = 44.0


def _alvo(seletor="a", x=0.0, y=0.0, largura=16.0, altura=16.0, **extra):
    return Caixa(seletor=seletor, x=x, y=y, largura=largura, altura=altura, **extra)


# ---------- Exceção "espaçamento": a que erra por arredondamento ----------

def test_espacamento_no_limite_exato_e_isento():
    """Encostar não é intersectar.

    Dois alvos pequenos com exatamente `minimo` entre centros têm círculos que
    se TOCAM. Tocar não é intersectar, e a norma fala de interseção. Um `<=` no
    lugar do `<` reprovaria o layout que cumpre a norma no limite — que é
    justamente o layout de quem leu a norma e a seguiu.
    """
    a = _alvo("a#um", x=0, y=0)
    b = _alvo("a#dois", x=MIN, y=0)          # centros a exatamente 24px
    assert excecao_de(a, [a, b], MIN) == "espacamento"


def test_espacamento_insuficiente_por_um_pixel_reprova():
    """1px a menos e os círculos se sobrepõem — não há exceção."""
    a = _alvo("a#um", x=0, y=0)
    b = _alvo("a#dois", x=MIN - 1, y=0)
    assert excecao_de(a, [a, b], MIN) == ""


def test_alvo_pequeno_perto_de_alvo_GRANDE_usa_circulo_contra_retangulo():
    """Contra alvo conforme, o teste é círculo × RETÂNGULO, não centro a centro.

    A diferença não é acadêmica: um botão de 200px de largura tem o centro longe
    e a borda perto. Comparar centros o daria como distante e perdoaria um alvo
    pequeno grudado na borda dele.
    """
    pequeno = _alvo("a#pequeno", x=0, y=0)                 # centro em (8, 8)
    grande = _alvo("button#grande", x=14, y=0, largura=200, altura=48)
    # Borda esquerda do grande em x=14; centro do pequeno em x=8 → distância 6 < raio 12.
    assert excecao_de(pequeno, [pequeno, grande], MIN) == ""


def test_alvo_pequeno_isolado_e_isento():
    solitario = _alvo("a#so")
    assert excecao_de(solitario, [solitario], MIN) == "espacamento"


def test_distancia_diagonal_conta_como_distancia():
    """Vizinho na diagonal não é vizinho distante: a norma fala de círculos, e
    círculo não tem cantos. Medir só em x ou só em y perdoaria a grade densa."""
    a = _alvo("a#um", x=0, y=0)
    b = _alvo("a#dois", x=15, y=15)          # ~21.2px entre centros, < 24
    assert excecao_de(a, [a, b], MIN) == ""


# ---------- Exceção "equivalente" ----------

def test_equivalente_exige_que_o_outro_controle_ATENDA_a_norma():
    """Dois alvos pequenos para a mesma ação não se salvam mutuamente.

    É o falso positivo invertido: um check que só perguntasse "existe outro
    controle com a mesma ação?" perdoaria uma página inteira de ícones de 16px
    duplicados.
    """
    icone = _alvo("a#icone", x=0, y=0, acao="/carrinho")
    outro_icone = _alvo("a#icone2", x=300, y=300, acao="/carrinho")
    assert excecao_de(icone, [icone, outro_icone], MIN) == "espacamento", (
        "isento por estar longe, não por equivalência — o outro também é pequeno")

    grande = _alvo("a#texto", x=300, y=300, largura=120, altura=40, acao="/carrinho")
    vizinho = _alvo("a#vizinho", x=10, y=0)     # cola no ícone: mata o espaçamento
    assert excecao_de(icone, [icone, vizinho, grande], MIN) == "equivalente"


def test_equivalente_sem_identidade_de_acao_nao_vale():
    """Sem `acao`, "equivalente" viraria "existe algum botão grande na página" —
    e isso perdoaria tudo."""
    sem_acao = _alvo("span#x", acao="")
    grande = _alvo("button#b", x=0, y=100, largura=48, altura=48, acao="")
    vizinho = _alvo("a#v", x=10, y=0, acao="/outra")
    assert excecao_de(sem_acao, [sem_acao, grande, vizinho], MIN) == ""


# ---------- Exceção "inline" ----------

def test_inline_vence_mesmo_grudado_em_outro_alvo():
    """Link dentro de frase é perdoado ainda que o espaçamento não ajude: o
    tamanho vem da entrelinha, não de escolha de quem desenhou."""
    dentro_da_frase = _alvo("a#link", x=0, y=0, inline=True)
    colado = _alvo("a#outro", x=5, y=0)
    assert excecao_de(dentro_da_frase, [dentro_da_frase, colado], MIN) == "inline"


# ---------- Classificação completa ----------

def test_ofensor_alerta_e_conforme_sao_separados():
    ofensor = _alvo("a#mini", x=0, y=0)
    vizinho = _alvo("a#colado", x=8, y=0)               # tira a exceção de espaçamento
    alerta = _alvo("button#medio", x=0, y=200, largura=30, altura=30)
    conforme = _alvo("button#bom", x=0, y=400, largura=48, altura=48)

    laudo = classificar_alvos([ofensor, vizinho, alerta, conforme], minimo=MIN, meta=META)
    assert {c.seletor for c in laudo.ofensores} == {"a#mini", "a#colado"}
    assert [c.seletor for c in laudo.alertas] == ["button#medio"]
    assert laudo.menor == 16.0


def test_alvo_retangular_nao_conta_como_conforme():
    """48x16 não atende: a norma exige 24 nas DUAS dimensões, e uma barra fina e
    larga é tão difícil de acertar quanto um quadradinho.

    Isolado, ele ainda é isento por espaçamento — o que a norma permite. O que
    NÃO pode acontecer é ele entrar como conforme ou como alerta, porque isso
    diria que a única pendência é a meta de 44px.
    """
    fino = _alvo("a#fino", largura=48, altura=16)
    laudo = classificar_alvos([fino], minimo=MIN, meta=META)
    assert laudo.alertas == () and laudo.ofensores == ()
    assert [i.caixa.seletor for i in laudo.isentos] == ["a#fino"]


def test_alvo_retangular_colado_no_vizinho_e_ofensor():
    """Sem a folga que o isentava, o lado curto governa e ele reprova."""
    fino = _alvo("a#fino", largura=48, altura=16)
    vizinho = _alvo("a#vizinho", x=10, y=0, largura=48, altura=16)
    laudo = classificar_alvos([fino, vizinho], minimo=MIN, meta=META)
    assert {c.seletor for c in laudo.ofensores} == {"a#fino", "a#vizinho"}


def test_sem_alvo_nenhum_o_menor_e_None_nunca_zero():
    """Ausência de medida não é alvo de 0px — §2.1 da casa. Zero num laudo de
    tamanho seria o pior alvo possível, e é o oposto do que aconteceu."""
    laudo = classificar_alvos([], minimo=MIN, meta=META)
    assert laudo.menor is None
    assert laudo.ofensores == () and laudo.alertas == ()


def test_isento_carrega_o_nome_da_excecao():
    """"Isento" sem motivo é indistinguível de "esquecido" — e quem audita o
    laudo precisa poder discordar da exceção aplicada."""
    solitario = _alvo("a#so")
    laudo = classificar_alvos([solitario], minimo=MIN, meta=META)
    assert [i.excecao for i in laudo.isentos] == ["espacamento"]


# ---------- Zoom (1.4.4) ----------

def test_perdas_comparam_conjuntos_e_ignoram_ordem():
    """A 200% tudo se move: comparar posição acusaria a ampliação como perda."""
    normal = {"marcos": ["h1:Loja", "button:Comprar"], "textos": ["um", "dois"]}
    ampliado = {"marcos": ["button:Comprar", "h1:Loja"], "textos": ["dois", "um"]}
    assert perdidos_entre(normal, ampliado).total == 0


def test_marco_que_some_e_perda_nomeada():
    normal = {"marcos": ["button:Comprar"], "textos": ["um"]}
    ampliado = {"marcos": [], "textos": ["um"]}
    perdas = perdidos_entre(normal, ampliado)
    assert perdas.marcos == ("button:Comprar",) and perdas.total == 1


def test_conteudo_novo_no_zoom_nao_conta_como_perda():
    """Só o que SUMIU é perda. Um alvo que revela conteúdo ao ampliar não está
    violando nada — e contar isso inverteria o critério."""
    normal = {"marcos": [], "textos": ["um"]}
    ampliado = {"marcos": ["nav:menu"], "textos": ["um", "dois"]}
    assert perdidos_entre(normal, ampliado).total == 0


def test_inventario_vazio_dos_dois_lados_nao_inventa_perda():
    assert perdidos_entre({}, {}).total == 0


# ---------- Evidência ----------

def test_resumo_traz_seletor_e_medida_e_trunca_com_contagem():
    caixas = [_alvo(f"a#i{i}", largura=16, altura=16) for i in range(12)]
    texto = resumo_de_caixas(caixas, teto=3)
    assert "a#i0 — 16x16px" in texto
    assert "e mais 9" in texto, "truncar sem dizer quantos ficaram esconde o tamanho do problema"


def test_resumo_de_isentos_nomeia_a_excecao():
    laudo = classificar_alvos([_alvo("a#so")], minimo=MIN, meta=META)
    assert "isento por espacamento" in resumo_de_isentos(laudo.isentos)


# ---------- Coletor: o que o navegador entrega ----------

@pytest.fixture(scope="module")
def navegador():
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


@pytest.mark.browser
def test_transform_scale_e_medido_pela_caixa_transformada(navegador):
    """`getBoundingClientRect` já traz a caixa TRANSFORMADA — e é ela que importa.

    Um botão de 40px com `transform: scale(.5)` ocupa 20px na tela: é o que o
    dedo encontra. Medir `offsetWidth` (40px) diria o que o CSS pediu e aprovaria
    um alvo que a pessoa não consegue acertar. Este teste é sobre o COLETOR, e
    por isso precisa de navegador — nenhuma caixa fabricada o provaria.
    """
    from webqa.geometria import JS_ALVOS_DE_TOQUE

    pagina = navegador.new_page()
    pagina.set_content("""
        <button id="normal" style="width:40px;height:40px">a</button>
        <button id="reduzido" style="width:40px;height:40px;transform:scale(.5)">b</button>
    """)
    por_id = {c["seletor"]: c for c in pagina.evaluate(JS_ALVOS_DE_TOQUE)}
    pagina.close()

    assert por_id["button#normal"]["largura"] == pytest.approx(40, abs=1)
    assert por_id["button#reduzido"]["largura"] == pytest.approx(20, abs=1), (
        "o coletor mediu o layout, não a caixa transformada — um alvo reduzido "
        "por transform passaria como confortável")


@pytest.mark.browser
def test_coletor_mede_o_clicavel_e_nao_o_icone_interno(navegador):
    """A área de toque costuma vir do padding do ancestral: medir o `<svg>`
    acusaria de pequeno um alvo confortável."""
    from webqa.geometria import JS_ALVOS_DE_TOQUE

    pagina = navegador.new_page()
    pagina.set_content("""
        <a id="acao" href="/x" style="display:inline-block;padding:16px">
          <svg width="8" height="8"><rect width="8" height="8"/></svg>
        </a>
    """)
    coletados = pagina.evaluate(JS_ALVOS_DE_TOQUE)
    pagina.close()

    assert [c["seletor"] for c in coletados] == ["a#acao"], "o svg interno não é alvo"
    assert coletados[0]["largura"] >= 40, "a caixa medida tem de incluir o padding do clicável"
