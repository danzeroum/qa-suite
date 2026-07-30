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
