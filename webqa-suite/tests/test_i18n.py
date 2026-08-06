"""VERIFICAÇÃO: pseudo-localização e perda de informação sob forced-colors (OS-52).

Inclui a **sonda** que decidiu o desenho do GUI-CONTR-03. Ela vira teste
permanente pela tradição do RGB/IDAT da OS-49: a decisão inteira depende de o
Chromium alterar o ESTILO COMPUTADO sob `forced-colors`, e um upgrade de
Playwright que mude isso não pode trocar o ramo em silêncio — trocaria um check
que mede por um check que dá verde permanente.
"""
import pytest

from webqa.i18n import (
    Distintivo,
    No,
    deve_expandir,
    expandir,
    informacao_perdida,
    perdeu_informacao,
    quebras_de,
    relato_de_perdas,
    resumo_de_quebras,
)

pytestmark = pytest.mark.verification


def _d(**extra) -> Distintivo:
    base = dict(seletor="span.x", fundo_normal="rgb(244, 244, 244)",
                fundo_forcado="rgb(255, 255, 255)", borda_normal="", borda_forcada="",
                fundo_de_referencia_normal="rgb(255, 255, 255)",
                fundo_de_referencia_forcado="rgba(255, 255, 255, 0)",
                tem_texto_proprio=False)
    return Distintivo(**{**base, **extra})


# ---------- expansão ----------

def test_paragrafo_expande():
    assert deve_expandir(No(tag="p", texto="Olá mundo")) is True


def test_campo_de_formulario_nao_expande():
    """Campo carrega DADO: um CEP expandido é um CEP errado."""
    assert deve_expandir(No(tag="input", texto="01001-000")) is False


def test_aria_hidden_fica_fora():
    assert deve_expandir(No(tag="span", texto="ícone", aria_hidden=True)) is False


def test_numero_puro_fica_fora():
    assert deve_expandir(No(tag="span", texto="1.234,56", so_numero=True)) is False


def test_conteudo_editavel_fica_fora():
    assert deve_expandir(No(tag="div", texto="rascunho", editavel=True)) is False


def test_texto_vazio_nao_expande():
    assert deve_expandir(No(tag="p", texto="   ")) is False


def test_um_caractere_ainda_expande():
    """A borda: 1 × 1,5 = 1,5, e truncar devolveria 1 — a expansão não
    aconteceria e o teste passaria anunciando que mediu."""
    assert expandir("a") == "aa"


def test_expansao_preserva_o_original_como_prefixo():
    """O laudo precisa continuar dizendo QUAL botão estourou."""
    assert expandir("Enviar").startswith("Enviar")


def test_expansao_cresce_cerca_de_metade():
    assert len(expandir("quatro")) == 9


def test_espaco_em_branco_atravessa_intacto():
    assert expandir("  ") == "  "


# ---------- forced-colors: o comparador ----------

def test_fundo_perdido_que_era_o_unico_distintivo_acusa():
    assert perdeu_informacao(_d()) is True


def test_fundo_perdido_com_texto_proprio_nao_acusa():
    """O texto sobrevive ao modo forçado e continua carregando o significado —
    WCAG 1.4.1 pelo avesso: quando a cor não é o único portador, forçar cor não
    tira nada."""
    assert perdeu_informacao(_d(tem_texto_proprio=True)) is False


def test_borda_que_sobrevive_nao_acusa():
    """O caso real do `.campo-erro` do alvo fabricado: sob forced-colors a borda
    permanece `solid` e só a cor muda. O distintivo atravessa."""
    assert perdeu_informacao(_d(fundo_normal="rgb(255, 255, 255)",
                                borda_normal="solid rgb(204, 0, 0)",
                                borda_forcada="solid rgb(0, 0, 0)")) is False


def test_mera_mudanca_de_cor_nao_acusa():
    """Mudar de cor é o que o modo FAZ. Acusar isso seria acusar o recurso."""
    assert perdeu_informacao(_d(fundo_normal="rgb(0, 0, 255)",
                                fundo_forcado="rgb(30, 30, 30)",
                                fundo_de_referencia_forcado="rgb(255, 255, 255)")) is False


def test_fundo_transparente_nao_e_distintivo():
    """A primeira regressão que a medição pegou: fundo `rgba(0,0,0,0)` comparado
    com o fundo EFETIVO do entorno acusava 12 perdas na home. Não distinguir
    nada não é distintivo a perder."""
    assert perdeu_informacao(_d(fundo_normal="rgba(0, 0, 0, 0)")) is False


def test_branco_com_alfa_zero_conta_como_transparente():
    """A SEGUNDA regressão, e a mais cara: o Chromium devolve
    `rgba(255, 255, 255, 0)` para o entorno sob forced-colors. Comparar strings
    fazia o elemento — que ficou idêntico ao entorno de fato — parecer diferente,
    e o comparador NÃO acusava. Verde permanente numa página com violação
    declarada. Este é o caso que a versão anterior teria deixado passar."""
    assert perdeu_informacao(_d(fundo_de_referencia_forcado="rgba(255, 255, 255, 0)")) is True


def test_informacao_perdida_filtra_e_preserva_ordem():
    perdidos = informacao_perdida([_d(seletor="a"), _d(seletor="b", tem_texto_proprio=True)])
    assert [d.seletor for d in perdidos] == ["a"]


def test_relato_nomeia_o_elemento_e_o_distintivo():
    texto = relato_de_perdas([_d(seletor="span.vazio")])
    assert "span.vazio" in texto and "fundo" in texto and "rgb(244, 244, 244)" in texto


# ---------- quebras ----------

def test_quebras_de_tolera_bruto_incompleto():
    """Instrumentação ilegível não pode derrubar a observação do alvo."""
    assert quebras_de([{}])[0].seletor == "?"


def test_resumo_ordena_pelas_maiores():
    q = quebras_de([{"seletor": "a", "motivo": "m", "px": 5},
                    {"seletor": "b", "motivo": "m", "px": 90}])
    assert resumo_de_quebras(q).splitlines()[0].strip().startswith("b:")


# ---------- a SONDA que decidiu o desenho ----------

@pytest.mark.browser
def test_forced_colors_altera_o_estilo_computado_e_nao_so_a_media_query():
    """**A sonda do ramo A|B da OS-52, fixada como contrato.**

    Todo o GUI-CONTR-03 depende disto: se `emulate_media(forced_colors=active)`
    virasse só a media query, comparar estilo computado entre os dois modos não
    mediria NADA e o check daria verde permanente — o verde indistinguível do
    legítimo que a pré-checagem de tema escuro da OS-45 existe para impedir.

    Medido no Chromium 1.56: o fundo pintado vira Canvas e a cor da borda vira a
    do sistema, mantendo `solid`. Ramo A. Um upgrade que mude isso reprova AQUI,
    com o motivo à mão, em vez de transformar o check num gerador de verde.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("Playwright não instalado (pip install playwright).")

    sonda = ("<!doctype html><html><head><style>"
             "body { background: #ffffff; }"
             ".pintado { background: #cc0000; width: 50px; height: 50px; }"
             ".comborda { border: 3px solid #00cc00; width: 50px; height: 50px; }"
             "</style></head><body>"
             "<div class='pintado'></div><div class='comborda'></div></body></html>")
    ler = ("() => ({bg: getComputedStyle(document.querySelector('.pintado')).backgroundColor,"
           " bc: getComputedStyle(document.querySelector('.comborda')).borderColor,"
           " bs: getComputedStyle(document.querySelector('.comborda')).borderStyle,"
           " mq: matchMedia('(forced-colors: active)').matches})")

    with sync_playwright() as p:
        try:
            navegador = p.chromium.launch()
        except Exception as exc:
            pytest.skip(f"chromium indisponível: {exc}")
        try:
            leituras = {}
            for rotulo, forcar in (("normal", False), ("forcado", True)):
                contexto = navegador.new_context()
                pagina = contexto.new_page()
                if forcar:
                    pagina.emulate_media(forced_colors="active")
                pagina.set_content(sonda)
                leituras[rotulo] = pagina.evaluate(ler)
                contexto.close()
        finally:
            navegador.close()

    assert leituras["normal"]["mq"] is False and leituras["forcado"]["mq"] is True, (
        "a media query `forced-colors: active` não acompanhou a emulação")
    assert leituras["normal"]["bg"] != leituras["forcado"]["bg"], (
        "RAMO B: o fundo pintado NÃO mudou sob forced-colors — comparar estilo "
        "computado deixou de medir alguma coisa, e o GUI-CONTR-03 apoiado nisso "
        f"virou verde permanente. Medido: {leituras}")
    assert leituras["normal"]["bc"] != leituras["forcado"]["bc"], (
        f"RAMO B: a cor da borda não mudou sob forced-colors. Medido: {leituras}")
    assert leituras["forcado"]["bs"] == leituras["normal"]["bs"], (
        "o ESTILO da borda mudou junto com a cor — o comparador isenta elemento "
        "cuja borda sobrevive, e essa isenção deixaria de valer")
