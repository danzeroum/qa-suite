"""VERIFICAÇÃO: o auditor de design acusa o que promete acusar.

Separação V&V: aqui o auditor é testado contra HTML FABRICADO em tmp_path; o
laudo sobre os arquivos reais do designer (docs/design-audit.md) é validação.

Se o auditor der PASS por engano, o gate deixa passar contrato visual quebrado —
e o §12 vira checklist decorativo.
"""
import pytest

from scripts.audita_design import (
    FAIL,
    NA,
    PASS,
    PULADO,
    Documento,
    Resultado,
    criterio_estados_sem_cor,
    criterio_funciona_sem_js,
    criterio_h1_unico,
    criterio_headings_sem_salto,
    criterio_lang,
    criterio_nota_epistemica,
    criterio_sem_vazamento_da_capa,
    criterio_tokens_custom_properties,
    criterio_zero_requisicao_externa,
    montar_laudo,
    veredito_axe,
)

pytestmark = pytest.mark.verification

CONFORME = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>t</title>
<style>:root{--cor-passed:#0a0;--cor-failed:#a00;--cor-xfail:#a60;--cor-skipped:#666;--acento:#00a}
@media print{@page{margin:15mm}.achado{break-inside:avoid}}
@media screen and (prefers-color-scheme:dark){:root{--cor-passed:#6f6}}</style></head>
<body><main><h1>Relatório</h1><section><h2>Panorama</h2>
<p class="failed"><svg class="ic" aria-hidden="true"></svg>8 achados</p>
<p>passar NÃO certifica conformidade</p></section></main>
<script>addEventListener("beforeprint",function(){})</script></body></html>"""


def _doc(tmp_path, html, nome="summary.html"):
    caminho = tmp_path / nome
    caminho.write_text(html, encoding="utf-8")
    return Documento(caminho, html)


# ---------- Casos de aceite da OS ----------

def test_img_externa_plantada_e_acusada(tmp_path):
    """Caso da OS: plantar <img src="https://x"> → acusa requisição externa."""
    doc = _doc(tmp_path, CONFORME.replace("<h1>", '<img src="https://x/y.png" alt="x"><h1>'))
    r = criterio_zero_requisicao_externa(doc)
    assert r.status == FAIL
    assert "img" in r.evidencia and "https://x" in r.evidencia
    assert "linha" in r.evidencia, "evidência precisa localizar o ofensor"


def test_componentes_sem_tokens_acusa_o_paragrafo_11_5(tmp_path):
    """Caso da OS: componentes.html sem custom properties → FAIL específico."""
    # Troca TODAS as declarações de token por cor literal — inclusive no bloco
    # escuro, que também as declara (é o mesmo bloco interpolado 2×).
    sem_tokens = (CONFORME.replace("--cor-passed:#0a0;", "").replace("--cor-passed:#6f6", "color:#6f6")
                  .replace("--acento:#00a", "color:#00a"))
    r = criterio_tokens_custom_properties(_doc(tmp_path, sem_tokens, "componentes.html"))
    assert r.status == FAIL
    assert "§11.5" in r.evidencia and "--cor-passed" in r.evidencia


# ---------- Vazamento da capa (o aviso prévio do review) ----------

@pytest.mark.parametrize("veneno", ["<x-dc-page>", "<helmet><title>t</title></helmet>",
                                    '<script src="support.js"></script>'])
def test_padroes_da_capa_sao_acusados(tmp_path, veneno):
    doc = _doc(tmp_path, CONFORME.replace("<h1>", veneno + "<h1>"))
    assert criterio_sem_vazamento_da_capa(doc).status == FAIL


# ---------- Critérios bloqueantes ----------

def test_lang_ausente_e_errado(tmp_path):
    assert criterio_lang(_doc(tmp_path, CONFORME)).status == PASS
    assert criterio_lang(_doc(tmp_path, CONFORME.replace(' lang="pt-BR"', ""))).status == FAIL
    assert criterio_lang(_doc(tmp_path, CONFORME.replace('lang="pt-BR"', 'lang="en"'))).status == FAIL


def test_h1_zero_e_h1_duplicado(tmp_path):
    assert criterio_h1_unico(_doc(tmp_path, CONFORME)).status == PASS
    sem_h1 = CONFORME.replace("<h1>Relatório</h1>", "<p>Relatório</p>")
    assert criterio_h1_unico(_doc(tmp_path, sem_h1)).status == FAIL
    dois = CONFORME.replace("<h2>Panorama</h2>", "<h1>Outro</h1>")
    assert criterio_h1_unico(_doc(tmp_path, dois)).status == FAIL


def test_js_externo_e_js_que_gera_conteudo(tmp_path):
    assert criterio_funciona_sem_js(_doc(tmp_path, CONFORME)).status == PASS
    externo = CONFORME.replace("<script>", '<script src="app.js"></script><script>')
    assert criterio_funciona_sem_js(_doc(tmp_path, externo)).status == FAIL
    gerador = CONFORME.replace('function(){}', 'function(){document.body.innerHTML="x"}')
    r = criterio_funciona_sem_js(_doc(tmp_path, gerador))
    assert r.status == FAIL and "gera conteúdo" in r.evidencia


def test_script_progressivo_de_impressao_nao_reprova(tmp_path):
    """O único JS do contrato (beforeprint) é opcional — não pode reprovar."""
    r = criterio_funciona_sem_js(_doc(tmp_path, CONFORME))
    assert r.status == PASS and "progressivo" in r.evidencia


# ---------- Critérios informativos ----------

def test_salto_de_heading(tmp_path):
    assert criterio_headings_sem_salto(_doc(tmp_path, CONFORME)).status == PASS
    salto = CONFORME.replace("<h2>Panorama</h2>", "<h4>Panorama</h4>")
    r = criterio_headings_sem_salto(_doc(tmp_path, salto))
    assert r.status == FAIL and "h1 → h4" in r.evidencia


def test_nota_epistemica_exigida_so_dos_relatorios(tmp_path):
    sem_nota = CONFORME.replace("passar NÃO certifica conformidade", "tudo certo")
    assert criterio_nota_epistemica(_doc(tmp_path, sem_nota)).status == FAIL
    # A especificação de componentes não é relatório de execução.
    assert criterio_nota_epistemica(_doc(tmp_path, sem_nota, "componentes.html")).status == NA


def test_estado_marcado_so_por_cor(tmp_path):
    assert criterio_estados_sem_cor(_doc(tmp_path, CONFORME)).status == PASS
    so_cor = CONFORME.replace('<svg class="ic" aria-hidden="true"></svg>8 achados', "")
    assert criterio_estados_sem_cor(_doc(tmp_path, so_cor)).status == FAIL


# ---------- Veredito do axe: ausência nunca é aprovação ----------

def test_axe_pulado_nunca_conta_como_pass():
    assert veredito_axe({}).status == PULADO
    pulado = {"test_sem_violacoes_criticas": "skipped", "test_sem_violacoes_serias": "skipped"}
    assert veredito_axe(pulado).status == PULADO
    ok = {"test_sem_violacoes_criticas": "passed", "test_sem_violacoes_serias": "passed"}
    assert veredito_axe(ok).status == PASS
    ruim = {"test_sem_violacoes_criticas": "failed", "test_sem_violacoes_serias": "passed"}
    r = veredito_axe(ruim)
    assert r.status == FAIL and "críticas" in r.evidencia


# ---------- Laudo ----------

def test_laudo_declara_veredito_e_bloqueios():
    linhas = {"summary.html": {'lang="pt-BR"': Resultado(FAIL, "AUSENTE")}}
    laudo = montar_laudo(linhas, ['`summary.html` — lang: AUSENTE'], {}, "cmd")
    assert "**Veredito: BLOQUEADO**" in laudo
    assert "não deve começar" in laudo and "AUSENTE" in laudo

    limpo = montar_laudo({"summary.html": {'lang="pt-BR"': Resultado(PASS, "ok")}}, [], {}, "cmd")
    assert "**Veredito: LIBERADO**" in limpo and "está liberada" in limpo


def test_laudo_atribui_artefatos_conhecidos():
    """Reprovação da bateria que não é do design tem de vir atribuída."""
    laudo = montar_laudo({"summary.html": {"x": Resultado(PASS)}}, [], {}, "cmd",
                         {"test_ajuda_no_erro_pagina_404_amigavel": ["summary.html"],
                          "test_novo": ["summary.html"]})
    assert "artefato do ARRANJO" in laudo, "reprovação do arranjo precisa vir atribuída"
    assert "a investigar" in laudo, "teste não classificado não pode passar como conhecido"
