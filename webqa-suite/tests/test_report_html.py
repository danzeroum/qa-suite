"""VERIFICAÇÃO: o relatório apresenta o que o código produziu, sem inventar nem
interpretar dado como marcação.

Unidade pura: nenhuma sessão pytest, nenhum navegador. A validação de sistema (a
bateria + o auditor de design contra o HTML gerado) fica em
tests/test_report_dogfooding.py.
"""
import re

import pytest

from webqa.report_html import (
    destaca_leis,
    duracao,
    esc,
    estado_de,
    montar,
    numero,
)
from webqa.report_style import ESTILO_CANONICO, ICONES

pytestmark = pytest.mark.verification


def _r(test, estado="passed", *, dimension="lgpd", dimensions=None, browser=False,
       detail="", duration_s=0.1):
    return {"test": test, "dimension": dimension, "dimensions": dimensions or [dimension],
            "browser": browser, "outcome": "skipped" if estado == "xfail" else estado,
            "estado": estado, "duration_s": duration_s, "detail": detail}


def _summary(results, **extra):
    base = {"generated_at": "2026-07-30 03:00:00", "duration_s": 12.3,
            "alvo": "https://alvo.com", "comando": "pytest -m lgpd",
            "by_dimension": {}, "dimension_notes": {"lgpd": "passar NÃO certifica conformidade"},
            "results": results}
    base.update(extra)
    return base


# ---------- Escape: dado nunca vira marcação ----------

def test_detail_com_metacaracteres_e_escapado_nunca_interpretado():
    veneno = '<script>alert("x")</script> & <b>bold</b> "aspas"'
    html = montar(_summary([_r("t::a", "failed", detail=veneno)]))
    assert "<script>alert" not in html, "conteúdo do alvo não pode virar marcação"
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "&amp;" in html and "&lt;b&gt;bold&lt;/b&gt;" in html


def test_nenhum_script_no_documento():
    """Contrato: sem JS obrigatório — o gerador não emite <script> nenhum."""
    html = montar(_summary([_r("t::a", "failed", detail="x")]))
    assert "<script" not in html.lower()


def test_id_de_teste_nunca_truncado():
    longo = "checks/lgpd/test_consentimento.py::test_" + "n" * 120
    html = montar(_summary([_r(longo, "failed", detail="x")]))
    assert esc(longo) in html


def test_escape_de_id_de_teste_com_metacaractere():
    html = montar(_summary([_r("t::test_a[<b>]", "failed", detail="x")]))
    assert "test_a[&lt;b&gt;]" in html


# ---------- Numeração e contagens ----------

def test_achados_numerados_de_a1_a_an_em_ordem():
    results = [_r(f"t::f{i}", "failed", detail=f"achado {i}") for i in range(1, 4)]
    html = montar(_summary(results))
    for i in (1, 2, 3):
        assert f'id="a{i}"' in html
        assert f'<span class="achado-id">A{i}</span>' in html
    assert html.index('id="a1"') < html.index('id="a2"') < html.index('id="a3"')


def test_alertas_numerados_e_fora_da_contagem_de_falhas():
    results = [_r("t::x1", "xfail", detail="Referrer-Policy ausente"),
               _r("t::x2", "xfail", detail="security.txt ausente")]
    html = montar(_summary(results))
    assert 'id="x1"' in html and 'id="x2"' in html
    assert "Achados (0)" in html, "alerta não pode entrar na contagem de achados"
    assert "Alertas (2)" in html


def test_banner_verde_e_alertas_coexistem():
    """Caso da OS: 0 failed + 3 xfail → banner verde E bloco de alertas."""
    results = [_r("t::p", "passed")] + [_r(f"t::x{i}", "xfail", detail=f"sinal {i}")
                                        for i in range(3)]
    html = montar(_summary(results))
    assert "Nenhuma não conformidade observada" in html
    assert "sinais de maturidade ausentes" in html
    assert 'id="x1"' in html and 'id="x3"' in html


def test_dupla_dimensao_aparece_uma_vez_com_sinalizacao():
    """Caso da OS: teste ux+lgpd aparece 1 vez, sinalizando dupla pertença."""
    results = [_r("checks/ux/test_a11y.py::test_alt", "failed",
                  dimension="ux", dimensions=["ux", "lgpd"], detail="imagem sem alt")]
    html = montar(_summary(results))
    assert html.count('id="a1"') == 1, "o teste não pode ser repetido por dimensão"
    assert html.count("test_alt</code>") == 1
    assert '<span class="chip-dim">ux</span>' in html
    assert '<span class="chip-dim">lgpd</span>' in html
    # O card de panorama conta nas duas dimensões.
    assert html.count('<span class="dim-nome">') == 2


# ---------- Variantes ----------

def test_variante_sem_alvo_nao_divide_por_zero():
    """Caso da OS: results vazio (só verification) → variante sem alvo."""
    html = montar(_summary([]))
    assert "Nenhum resultado registrado" in html
    assert "Nenhum resultado para listar" in html
    assert "<h1>" in html and "0" in html


def test_variante_sem_navegador_mostra_o_comando_que_resolve():
    results = [_r("checks/ux/test_a11y.py::test_axe", "skipped", browser=True,
                  detail="Chromium indisponível: rode `python -m playwright install chromium`")]
    html = montar(_summary(results))
    assert "Chromium indisponível neste ambiente" in html
    assert "python -m playwright install chromium" in html
    assert "Chromium indispon" in html.split("<details")[1], "motivo visível na tabela"


def test_variante_parcial_declara_o_que_nao_foi_avaliado():
    results = [_r("checks/lgpd/test_x.py::test_a", "failed", detail="achado")]
    html = montar(_summary(results))
    assert "Execução parcial" in html and "ausência de achado" in html


def test_execucao_normal_nao_declara_parcial_nem_verde():
    results = [_r("t::a", "failed", dimension="lgpd", detail="x"),
               _r("t::b", "passed", dimension="ux")]
    html = montar(_summary(results))
    assert "Execução parcial" not in html
    assert "Nenhuma não conformidade" not in html


# ---------- Nota epistêmica e ausência de selo ----------

def test_nota_epistemica_vem_verbatim_de_dimension_notes():
    nota = ("Verificação caixa-preta do que é observável de fora. Falha PROVA não "
            "conformidade; passar NÃO certifica conformidade — base legal não é observável.")
    html = montar(_summary([_r("t::a", "failed", detail="x")], dimension_notes={"lgpd": nota}))
    assert esc(nota) in html, "o template APRESENTA a nota, não a reescreve"
    assert "constitui selo, certificação ou aprovação" in html


def test_dimensao_sem_nota_nao_ganha_bloco_epistemico():
    html = montar(_summary([_r("t::a", "passed", dimension="backend")], dimension_notes={}))
    # A classe existe na folha canônica; o que não pode existir é o BLOCO no corpo.
    corpo = html.split("</style>", 1)[1]
    assert 'class="nota-epistemica"' not in corpo


# ---------- Terceiros ----------

def test_terceiros_ausente_declara_ausencia():
    html = montar(_summary([_r("t::a", "passed")]), terceiros=None)
    assert "não foi gerado" in html


def test_terceiros_vazio_declara_nenhum_contactado():
    html = montar(_summary([_r("t::a", "passed")]), terceiros={"third_parties": []})
    assert "Nenhum terceiro contactado" in html


def test_terceiros_classifica_tracker_e_liga_ao_achado():
    results = [_r("t::trackers", "failed", detail="rastreador www.googletagmanager.com disparou")]
    inventario = {"third_parties": [
        {"host": "www.googletagmanager.com", "requests": 2, "resource_types": ["script"]},
        {"host": "cdn.alvo-parceiro.example", "requests": 1, "resource_types": ["script"]}]}
    html = montar(_summary(results), terceiros=inventario)
    assert "consta em TRACKER_DOMAINS" in html
    assert "não classificado" in html
    assert 'ver <a href="#a1">A1</a>' in html


def test_allowlist_desclassifica_tracker_no_inventario():
    inventario = {"third_parties": [{"host": "www.googletagmanager.com", "requests": 1,
                                     "resource_types": ["script"]}]}
    html = montar(_summary([_r("t::a", "passed")]), terceiros=inventario,
                  allowlist=["googletagmanager.com"])
    assert "consta em TRACKER_DOMAINS" not in html


# ---------- Primitivas ----------

def test_numeros_em_pt_br():
    assert numero(41.7, 1) == "41,7"
    assert duracao(0.021) == "0,021 s"
    assert duracao(41.7) == "41,7 s"


def test_destaque_de_lei_roda_depois_do_escape():
    escapado = esc("viola o Art. 7º, I e o Art. 46 da LGPD")
    marcado = destaca_leis(escapado)
    assert '<strong class="lei">Art. 7º, I</strong>' in marcado
    assert '<strong class="lei">Art. 46</strong>' in marcado


def test_destaque_de_lei_nao_reabre_marcacao_escapada():
    """Se o alvo mandar '<strong>', ele continua escapado depois do destaque."""
    marcado = destaca_leis(esc("<strong>Art. 9º</strong>"))
    assert "&lt;strong&gt;" in marcado
    assert marcado.count('<strong class="lei">') == 1


def test_estado_de_prefere_o_campo_estado():
    assert estado_de({"outcome": "skipped", "estado": "xfail"}) == "xfail"
    assert estado_de({"outcome": "failed"}) == "failed"
    assert estado_de({}) == "skipped"


# ---------- Dimensão `gui` (OS-41) ----------
#
# A dimensão só existe de verdade quando ATRAVESSA os quatro pontos: marcador,
# DIMENSIONS, DIMENSION_NOTES e OBSERVACOES. Testar a constante provaria que o
# texto foi escrito; o que estes testes exigem é que ele chegue à PÁGINA — é a
# diferença entre "a garantia existe" e "a ligação existe"
# (docs/PROXIMOS-PASSOS.md §2.10).

def test_gui_e_dimensao_reconhecida_e_nao_cai_em_other():
    """Fora de `report.py::DIMENSIONS` a dimensão agrupa como `other`: existiria
    no pytest e não no laudo, que é o pior dos dois mundos — os checks rodam e
    ninguém lê o resultado."""
    from webqa.report import DIMENSIONS

    assert "gui" in DIMENSIONS


def test_card_de_gui_renderiza_com_observacao():
    html = montar(_summary([_r("t::a", "failed", dimension="gui", detail="alvo de 16px")]))
    assert ">gui<" in html, "a dimensão não ganhou card no panorama"
    assert "Interface renderizada" in html, "a observação do card não foi interpolada"


def test_nota_epistemica_de_gui_chega_ao_html():
    """A nota é o que impede o laudo de virar selo. Ela vive em
    `report.py::DIMENSION_NOTES`, viaja no `summary` e tem de aparecer no card —
    quem lê o relatório não leu o contrato da dimensão.
    """
    from webqa.report import DIMENSION_NOTES

    nota = DIMENSION_NOTES["gui"]
    html = montar(_summary([_r("t::a", "passed", dimension="gui")],
                           dimension_notes={"gui": nota}))
    assert "NÃO certifica usabilidade" in html
    assert "geometria conforme" in html


def test_gui_nao_inventa_classe_fora_da_folha_canonica():
    """Zero classe nova: a folha é congelada byte a byte, e inventar token é
    regressão, não melhoria (§2.4). Mesma varredura que o painel já sofre."""
    html = montar(_summary([_r("t::a", "failed", dimension="gui", detail="x"),
                            _r("t::b", "xfail", dimension="gui", detail="y")]))
    corpo = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    usadas = {c for m in re.finditer(r'class="([^"]+)"', corpo) for c in m.group(1).split()}
    ausentes = sorted(c for c in usadas if f".{c}" not in ESTILO_CANONICO)
    assert ausentes == [], f"classes sem regra na folha canônica: {ausentes}"


def test_gui_convive_com_as_outras_dimensoes():
    """Dimensão nova não pode reordenar nem engolir as antigas — um laudo
    anterior tem de renderizar exatamente como antes."""
    html = montar(_summary([_r("t::a", "passed", dimension="lgpd"),
                            _r("t::b", "failed", dimension="gui", detail="x"),
                            _r("t::c", "passed", dimension="seguranca")]))
    for dim in ("lgpd", "gui", "seguranca"):
        assert f">{dim}<" in html


# ---------- Contrato visual ----------

def test_estilo_canonico_embutido_uma_vez_e_sem_requisicao_externa():
    html = montar(_summary([_r("t::a", "passed")]))
    assert html.count("<style>") == 1
    assert ESTILO_CANONICO in html, "a folha canônica entra verbatim"
    assert not re.search(r'(src|href)="https?://', html.replace("http://www.w3.org", ""))


def test_quatro_estados_com_forma_e_rotulo():
    results = [_r("t::a", "failed", detail="x"), _r("t::b", "xfail", detail="y"),
               _r("t::c", "passed"), _r("t::d", "skipped", detail="motivo")]
    html = montar(_summary(results))
    for estado, rotulo in (("failed", "achado"), ("xfail", "alerta"),
                           ("passed", "passou"), ("skipped", "pulado")):
        assert ICONES[estado] in html, f"forma do estado {estado} ausente"
        assert f">{rotulo}</span>" in html, f"rótulo textual do estado {estado} ausente"
    assert 'aria-hidden="true"' in html


def test_tamanho_com_200_resultados():
    results = [_r(f"checks/lgpd/test_m{i}.py::test_caso_{i}",
                  "failed" if i % 20 == 0 else "passed",
                  detail="Detalhe do achado com Art. 46 citado." if i % 20 == 0 else "")
               for i in range(200)]
    html = montar(_summary(results))
    kb = len(html.encode("utf-8")) / 1024
    assert kb < 300, f"{kb:.0f} KB estoura o orçamento de 300 KB"


def test_ordem_das_secoes_segue_o_paragrafo_6():
    results = [_r("t::a", "failed", detail="x"), _r("t::b", "xfail", detail="y")]
    html = montar(_summary(results), terceiros={"third_parties": []})
    posicoes = [html.index(m) for m in ('id="panorama"', 'id="achados"', 'id="alertas"',
                                        'id="terceiros"', 'id="tabela"', "<footer>")]
    assert posicoes == sorted(posicoes), "ordem do §6 violada"
    assert html.index("nota-epistemica") < html.index('id="achados"')


# ---------- OS-20: estado `error`, faixa de métricas, julgamento incompleto ----------

def _e(test, *, dimension="frontend", fase="setup", detail="Page.goto: net::ERR_CONNECTION_RESET"):
    """Erro de infraestrutura como webqa/report.py o grava: outcome failed, estado error."""
    return {"test": test, "dimension": dimension, "dimensions": [dimension], "browser": True,
            "outcome": "failed", "estado": "error", "fase": fase,
            "duration_s": 13.2, "detail": detail}


def test_error_nao_e_lido_como_failed_pelo_outcome():
    """O pytest reporta erro de setup com outcome=failed.

    Cair no `outcome` faria toda fixture quebrada virar não conformidade DO ALVO —
    um navegador que não subiu acusaria o site.
    """
    assert estado_de({"outcome": "failed", "estado": "error"}) == "error"


def test_error_jamais_soma_em_achados():
    html = montar(_summary([_r("t::ok", "passed"), _e("checks/frontend/t.py::test_fcp")]))
    assert "Achados (0)" in html, "erro de infra não é achado"
    assert "Erros de execução (1)" in html


def test_xfail_jamais_soma_em_falhas_mesmo_com_erros():
    results = [_r("t::x", "xfail", detail="Referrer-Policy ausente"),
               _e("checks/frontend/t.py::test_fcp")]
    html = montar(_summary(results))
    assert "Achados (0)" in html
    assert "Alertas (1)" in html and "Erros de execução (1)" in html


def test_zero_achados_com_erros_nao_da_banner_verde():
    """Caso da OS: 0 failed + errors>0 → 'julgamento incompleto', não elogio."""
    html = montar(_summary([_r("t::ok", "passed"), _e("checks/frontend/t.py::test_fcp")]))
    assert "Julgamento incompleto" in html
    assert "Nenhuma não conformidade observada nesta execução." not in html, (
        "a frase de sucesso não pode aparecer sem ressalva quando a infra quebrou")
    assert "entre os testes que conseguiram rodar" in html


def test_zero_achados_sem_erros_mantem_o_banner_verde():
    html = montar(_summary([_r("t::ok", "passed")]))
    assert "Nenhuma não conformidade observada" in html
    assert "Julgamento incompleto" not in html


def test_secao_de_erros_e_neutra_sem_cor_de_estado():
    """A folha canônica não define `.error`; inventar cor seria divergir."""
    html = montar(_summary([_e("checks/frontend/t.py::test_fcp")]))
    corpo = html.split("</style>", 1)[1]
    secao = corpo.split('id="erros"', 1)[1].split("</section>", 1)[0]
    assert 'class="chip-neutro"' in secao and "fora-escopo" in secao
    for classe in ("estado failed", "estado xfail", "estado passed", "estado skipped"):
        assert classe not in secao, f"seção de infra não pode usar {classe}"
    assert 'class="error"' not in corpo and "cor-error" not in corpo


def test_secao_de_erros_some_quando_nao_ha_erros():
    html = montar(_summary([_r("t::ok", "passed")]))
    assert 'id="erros"' not in html


def test_ordem_do_paragrafo_6_com_a_secao_de_erros():
    results = [_r("t::a", "failed", detail="x"), _r("t::b", "xfail", detail="y"),
               _e("checks/frontend/t.py::test_fcp")]
    html = montar(_summary(results), terceiros={"third_parties": []})
    posicoes = [html.index(m) for m in ('id="panorama"', 'id="achados"', 'id="alertas"',
                                        'id="erros"', 'id="terceiros"', 'id="tabela"')]
    assert posicoes == sorted(posicoes), "erros fica entre alertas e terceiros"


def test_numeracao_das_secoes_acompanha_a_presenca_da_de_erros():
    """Índice e cabeçalhos saem da MESMA lista — não podem discordar."""
    sem = montar(_summary([_r("t::ok", "passed")]))
    com = montar(_summary([_r("t::ok", "passed"), _e("checks/frontend/t.py::test_fcp")]))
    assert '<span class="n">4</span>Inventário' in sem
    assert '<span class="n">5</span>Inventário' in com
    assert '<span class="n">4</span>Erros de execução' in com


def test_error_na_tabela_sai_sem_selo_colorido():
    html = montar(_summary([_e("checks/frontend/t.py::test_fcp")]))
    linha = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert '<span class="chip-neutro">erro de infra</span>' in linha
    assert 'class="estado-min error"' not in linha


def test_dimensao_so_com_erros_nao_sai_como_sem_achados():
    html = montar(_summary([_e("checks/frontend/t.py::test_fcp")]))
    assert "não avaliada" in html
    assert "1 erro de infra" in html


# ---------- Faixa de métricas ----------

def test_faixa_de_metricas_mostra_so_o_que_foi_medido():
    html = montar(_summary([_r("t::ok", "passed")],
                           metricas={"ttfb_ms": 108.4, "total_ms": 109.2, "cls": 0.021}))
    faixa = html.split('id="metricas"', 1)[1].split("</dl>", 1)[0]
    assert "TTFB" in faixa and "108 ms" in faixa
    assert "CLS" in faixa and "0,021" in faixa
    assert "FCP" not in faixa and "LCP" not in faixa, "métrica ausente não aparece"


def test_metricas_ausentes_omitem_a_faixa_inteira_sem_zeros_falsos():
    """Caso da OS: ausente ≠ zero. Zero num relatório de performance é elogio."""
    html = montar(_summary([_r("t::ok", "passed")]))
    assert 'id="metricas"' not in html
    assert "TTFB" not in html and "FCP" not in html


def test_metrica_nula_nao_vira_zero():
    html = montar(_summary([_r("t::ok", "passed")],
                           metricas={"ttfb_ms": 90.0, "fcp_ms": None}))
    faixa = html.split('id="metricas"', 1)[1].split("</dl>", 1)[0]
    assert "TTFB" in faixa and "FCP" not in faixa


def test_metrica_ilegivel_nao_derruba_o_relatorio():
    html = montar(_summary([_r("t::ok", "passed")],
                           metricas={"ttfb_ms": "n/a", "total_ms": 50.0}))
    faixa = html.split('id="metricas"', 1)[1].split("</dl>", 1)[0]
    assert "Download total" in faixa and "TTFB" not in faixa


# ---------- Regressão do placeholder literal ----------

@pytest.mark.parametrize("results", [
    [],
    [_r("t::ok", "passed")],
    [_r("t::a", "failed", detail="x")],
    [_r("t::x", "xfail", detail="y")],
    [_r("t::ok", "passed"), _e("checks/frontend/t.py::test_fcp")],
])
def test_nenhum_placeholder_literal_chega_ao_html(results):
    """Regressão: blocos sem prefixo `f` emitiam `{ACHADOS_VAZIO}` no relatório
    VERDE — o caso em que essa é a única frase da seção."""
    html = montar(_summary(results))
    corpo = html.split("</style>", 1)[1]
    assert not re.findall(r"\{[A-Z_]{4,}\}", corpo), "placeholder de f-string vazou para o HTML"


def test_achados_vazio_com_erros_nao_usa_a_caixa_verde():
    """Cor não pode contradizer texto: `.vazio` é verde no contrato."""
    com = montar(_summary([_r("t::ok", "passed"), _e("checks/frontend/t.py::test_fcp")]))
    secao = com.split('id="achados"', 1)[1].split("</section>", 1)[0]
    assert "fora-escopo" in secao and "intro-sec vazio" not in secao
    sem = montar(_summary([_r("t::ok", "passed")]))
    secao_verde = sem.split('id="achados"', 1)[1].split("</section>", 1)[0]
    assert "intro-sec vazio" in secao_verde, "sem erros, a caixa verde é correta"


# ---------- OS-23: severidade tipográfica e fase (dimensão seguranca) ----------

def _s(test, severidade=None, fase=None, **kw):
    r = _r(test, "failed", dimension="seguranca", dimensions=["seguranca"],
           detail=kw.pop("detail", "achado"), **kw)
    if severidade:
        r["severidade"] = severidade
    if fase:
        r["fase_seguranca"] = fase
    return r


def test_severidade_e_rotulo_mono_e_nunca_cor_nova():
    """Regra do §5: severidade é TIPOGRÁFICA. Nenhum tom fora dos 4 estados."""
    html = montar(_summary([_s("t::a", "alta", "A")]))
    assert ">sev. alta</span>" in html
    corpo = html.split("</style>", 1)[1]
    assert "var(--mono)" in corpo, "o rótulo usa a fonte mono do contrato"
    for inventado in ("--cor-alta", "--cor-media", "--cor-severidade", 'class="alta"'):
        assert inventado not in corpo, f"sub-semáforo dentro de failed: {inventado}"


def test_ordenacao_alta_antes_de_media_e_baixa():
    results = [_s("t::baixa", "baixa", "A"), _s("t::media", "media", "A"),
               _s("t::alta", "alta", "A")]
    html = montar(_summary(results))
    assert html.index("t::alta") < html.index("t::media") < html.index("t::baixa")


def test_achado_sem_severidade_mantem_a_margem_intacta():
    """Caso da OS: dimensões antigas não têm o campo — layout não pode quebrar."""
    html = montar(_summary([_r("t::antigo", "failed", detail="x")]))
    assert "sev." not in html
    assert '<div class="achado-margem"><span class="achado-id">A1</span>' in html


def test_sem_severidade_vai_depois_dos_classificados():
    results = [_r("t::antigo", "failed", dimension="seguranca",
                  dimensions=["seguranca"], detail="x"),
               _s("t::alta", "alta", "A")]
    html = montar(_summary(results))
    assert html.index("t::alta") < html.index("t::antigo")


def test_fase_entra_como_chip_dim_sem_componente_novo():
    html = montar(_summary([_s("t::a", "alta", "A")]))
    assert '<span class="chip-dim">fase A</span>' in html
    assert '<span class="chip-dim">seguranca</span>' in html


def test_fase_de_execucao_nao_vira_chip():
    """`fase` (setup/call/teardown) é outro campo — não pode virar chip A/B/C."""
    resultado = _r("t::a", "failed", detail="x")
    resultado["fase"] = "call"
    html = montar(_summary([resultado]))
    assert "chip-dim\">fase call" not in html


def test_evidencia_mascarada_chega_pronta_e_nao_e_reescapada():
    """Caso da OS: AKIA**** em <code>, sem escape duplo."""
    detalhe = "Segredo em <code>/static/app.js</code>: AKIA****************"
    html = montar(_summary([_s("t::a", "alta", "A", detail=detalhe)]))
    assert "AKIA****************" in html
    assert "&amp;lt;" not in html, "escape duplo"


def test_nenhuma_coordenada_gps_em_claro():
    detalhe = "1 imagem publicada com coordenada GPS no EXIF (valor não reproduzido)"
    html = montar(_summary([_s("t::gps", "alta", "B", detail=detalhe)]))
    assert "não reproduzido" in html
    assert not re.search(r"-?\d{1,3}\.\d{4,}", html), "coordenada em claro no HTML"


def test_nao_avaliado_usa_xfail_com_motivo_e_fora_da_soma_de_falha():
    """Corpo truncado: xfail com motivo, jamais somado a achados."""
    motivo = "não avaliado: 800000 bytes excedem o teto de 512000"
    html = montar(_summary([_r("t::truncado", "xfail", dimension="seguranca",
                               dimensions=["seguranca"], detail=motivo)]))
    assert "Achados (0)" in html and "Alertas (1)" in html
    assert "excedem o teto" in html


def test_summary_sem_seguranca_renderiza_identico_ao_anterior():
    """Retrocompatibilidade: campo opcional não pode mudar um byte do que existia."""
    results = [_r("t::a", "failed", detail="x"), _r("t::b", "xfail", detail="y"),
               _r("t::c", "passed")]
    base = montar(_summary(results))
    assert "sev." not in base and "fase " not in base
    # E o mesmo summary com o campo AUSENTE (não vazio) produz o mesmo byte.
    assert montar(_summary([dict(r) for r in results])) == base


# ---------- OS-34: derivação E presença, o par que o #31 mostrou faltar ----------

def test_contagem_por_dimensao_derivada_e_presente_no_html():
    """O par completo: a conta certa E a conta na página.

    Só a primeira metade é o furo do #31: `motivos_do_zero` calculava certo,
    tinha teste de retorno verde, e o bloco não estava interpolado. Aqui a
    contagem por dimensão é conferida como DADO e depois procurada no HTML
    renderizado — se `_panorama` sair do template, este teste cai.
    """
    from webqa.report_html import _por_dimensao

    results = [
        _r("checks/lgpd/a.py::t1", "failed", dimension="lgpd", detail="x"),
        _r("checks/lgpd/b.py::t2", "passed", dimension="lgpd"),
        _r("checks/ux/c.py::t3", "xfail", dimension="ux", detail="y"),
    ]
    # Verificação: a derivação separa as dimensões como se espera.
    por_dim = _por_dimensao(results)
    assert sorted(por_dim) == ["lgpd", "ux"]
    assert len(por_dim["lgpd"]) == 2 and len(por_dim["ux"]) == 1

    # Validação: os nomes derivados chegam à página, no card de panorama.
    html = montar(_summary(results))
    assert '<span class="dim-nome">lgpd</span>' in html
    assert '<span class="dim-nome">ux</span>' in html
    assert html.count('<span class="dim-nome">') == 2


def test_panorama_sem_resultado_e_vazio_legitimo_e_nao_ausencia():
    """Distinção que o teste de retorno sozinho não faz.

    Sem resultados o panorama legitimamente não tem card nenhum — e a página
    continua válida, com a seção presente e a explicação no lugar do conteúdo.
    Isso é diferente de a seção ter sumido do template.
    """
    html = montar(_summary([]))
    assert 'id="panorama"' in html, "a seção precisa existir mesmo vazia"
    assert '<span class="dim-nome">' not in html, "sem dimensão, sem card"
    assert "Nenhum resultado registrado" in html
