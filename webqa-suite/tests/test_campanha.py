"""VERIFICAÇÃO do consolidador da campanha — sem rede, sem pytest interno.

A campanha é o nível SISTEMA da suíte, e um consolidador que erra é pior que
consolidador nenhum: ele produz número plausível. Os riscos que importam:

* **mediana escondendo pior caso** — o alvo intermitente parecendo saudável;
* **instabilidade agregada em média** — 2×passed 1×failed virando "67% passou",
  que é a leitura que faz um flake ser ignorado por um trimestre;
* **ausência de amostra contada como zero** — FCP não emitido virando "0ms",
  o elogio mais falso que um relatório de performance pode dar;
* **um alvo fora do ar derrubando a campanha inteira** — as outras medidas,
  perfeitamente válidas, perdidas junto.

A validação (execução real contra os três alvos) fica no PR, não aqui: teste que
depende de terceiro no ar não é verificação, é aposta.
"""
from __future__ import annotations

import pytest

from scripts.campanha import (
    Alvo,
    Campanha,
    CampanhaAbortada,
    ResultadoAlvo,
    consolidar,
    duracoes_por_teste,
    env_da_execucao,
    estados_por_teste,
    instabilidades,
    mais_lentos,
    placar,
    por_dimensao,
    render_markdown,
    resumo,
    rodar,
    verificar_ambiente_passivo,
)

pytestmark = pytest.mark.verification

ALVO = Alvo(url="https://alvo.example", papel="controle", crawl_max_pages=5)


def _summary(*, ttfb, total, fcp=None, cls=0.02, results, duration_s=40.0):
    """Summary no formato que webqa/report.py grava."""
    metricas = {"ttfb_ms": ttfb, "total_ms": total, "cls": cls}
    if fcp is not None:
        metricas["fcp_ms"] = fcp
    return {"generated_at": "2026-07-30 04:00:00", "duration_s": duration_s,
            "alvo": ALVO.url, "comando": "pytest", "metricas": metricas,
            "results": results}


def _r(test, estado="passed", *, dimension="backend", duration_s=0.5):
    return {"test": test, "dimension": dimension, "dimensions": [dimension],
            "browser": False, "outcome": "skipped" if estado == "xfail" else estado,
            "estado": estado, "duration_s": duration_s, "detail": ""}


def _tres_execucoes():
    """Três repetições do mesmo alvo, com UM teste divergindo (2×passed 1×failed)."""
    return [
        _summary(ttfb=100.0, total=300.0, fcp=800.0, results=[
            _r("checks/backend/test_a.py::test_estavel"),
            _r("checks/backend/test_b.py::test_oscila"),
            _r("checks/frontend/test_c.py::test_lento", dimension="frontend", duration_s=3.0),
        ]),
        _summary(ttfb=900.0, total=2000.0, fcp=None, results=[
            _r("checks/backend/test_a.py::test_estavel"),
            _r("checks/backend/test_b.py::test_oscila", "failed"),
            _r("checks/frontend/test_c.py::test_lento", dimension="frontend", duration_s=9.0),
        ], duration_s=95.0),
        _summary(ttfb=200.0, total=400.0, fcp=850.0, results=[
            _r("checks/backend/test_a.py::test_estavel"),
            _r("checks/backend/test_b.py::test_oscila"),
            _r("checks/frontend/test_c.py::test_lento", dimension="frontend", duration_s=3.2),
        ]),
    ]


def _consolidado(resultados):
    return consolidar(resultados, gerado_em="2026-07-30 05:00:00",
                      parede_total_s=310.5, repeticoes=3)


# ---------- Mediana E pior caso ----------

def test_resumo_traz_mediana_e_pior_caso():
    assert resumo([100.0, 900.0, 200.0]) == {"mediana": 200.0, "pior": 900.0, "n": 3}


def test_resumo_sem_amostra_e_none_e_nao_zero():
    """Ausência não é zero: zero viraria 'instantâneo' no consolidado."""
    assert resumo([]) is None
    assert resumo([None, None]) is None


def test_consolidado_calcula_mediana_e_pior_das_metricas_do_alvo():
    dados = _consolidado([ResultadoAlvo(ALVO, execucoes=_tres_execucoes())])
    ttfb = dados["alvos"][0]["metricas"]["ttfb_ms"]
    assert ttfb["mediana"] == 200.0, "mediana de 100/900/200"
    assert ttfb["pior"] == 900.0, "o pior caso não pode ser suavizado"
    assert dados["alvos"][0]["metricas"]["total_ms"]["pior"] == 2000.0


def test_metrica_ausente_em_uma_repeticao_e_declarada_nao_interpolada():
    """FCP medido em 2 de 3 execuções: n=2 e 1 faltando, não média de três."""
    dados = _consolidado([ResultadoAlvo(ALVO, execucoes=_tres_execucoes())])
    fcp = dados["alvos"][0]["metricas"]["fcp_ms"]
    assert fcp["n"] == 2 and fcp["faltando"] == 1
    assert fcp["mediana"] == 825.0, "média das 2 amostras REAIS, sem o zero fantasma"
    assert "sem amostra" in render_markdown(dados)


# ---------- Instabilidade 2×1 ----------

def test_instabilidade_2x1_e_marcada_sem_media_escondendo():
    achados = instabilidades(_tres_execucoes())
    assert len(achados) == 1, "só o teste que oscilou entra"
    assert achados[0]["test"] == "checks/backend/test_b.py::test_oscila"
    assert achados[0]["placar"] == "2×passed 1×failed"


def test_placar_ordena_do_mais_frequente_ao_menos():
    from collections import Counter
    assert placar(Counter({"passed": 2, "failed": 1})) == "2×passed 1×failed"


def test_teste_que_desaparece_numa_repeticao_conta_como_instavel():
    """Sumir da coleta é instabilidade: sem isso, 2 de 3 execuções passa por estável."""
    execucoes = _tres_execucoes()
    execucoes[1]["results"] = [r for r in execucoes[1]["results"]
                               if "test_estavel" not in r["test"]]
    achados = {a["test"]: a["placar"] for a in instabilidades(execucoes)}
    assert "1×ausente" in achados["checks/backend/test_a.py::test_estavel"]


def test_teste_estavel_nao_aparece_como_instavel():
    achados = [a["test"] for a in instabilidades(_tres_execucoes())]
    assert "checks/backend/test_a.py::test_estavel" not in achados


def test_markdown_mostra_o_placar_e_nao_um_percentual():
    dados = _consolidado([ResultadoAlvo(ALVO, execucoes=_tres_execucoes())])
    md = render_markdown(dados)
    assert "2×passed 1×failed" in md
    assert "67%" not in md and "66%" not in md


# ---------- Dimensões e variação ----------

def test_contagem_por_dimensao_expoe_a_variacao_entre_repeticoes():
    dims = por_dimensao(_tres_execucoes())
    passed = dims["backend"]["estados"]["passed"]
    assert (passed["min"], passed["max"]) == (1, 2), "backend oscila entre 1 e 2 passed"
    failed = dims["backend"]["estados"]["failed"]
    assert (failed["min"], failed["max"]) == (0, 1)


def test_markdown_imprime_faixa_quando_a_contagem_variou():
    dados = _consolidado([ResultadoAlvo(ALVO, execucoes=_tres_execucoes())])
    assert "1–2" in render_markdown(dados), "faixa marca a variação; número único a apagaria"


def test_tempo_somado_por_dimensao_traz_mediana_e_pior():
    dims = por_dimensao(_tres_execucoes())
    frontend = dims["frontend"]["tempo_s"]
    assert frontend["mediana"] == 3.2 and frontend["pior"] == 9.0


# ---------- Top-5 mais lentos ----------

def test_mais_lentos_ranqueia_pela_mediana_com_pior_ao_lado():
    ranking = mais_lentos(_tres_execucoes())
    assert ranking[0]["test"] == "checks/frontend/test_c.py::test_lento"
    assert ranking[0]["mediana_s"] == 3.2, "mediana de 3,0/9,0/3,2 — não a média"
    assert ranking[0]["pior_s"] == 9.0


def test_mais_lentos_respeita_o_limite():
    execucoes = [_summary(ttfb=10.0, total=20.0, results=[
        _r(f"t::test_{i}", duration_s=float(i)) for i in range(20)])]
    assert len(mais_lentos(execucoes, limite=5)) == 5


# ---------- Alvo inacessível ----------

def test_alvo_inacessivel_nao_derruba_a_campanha_e_e_declarado(tmp_path):
    """Caso da OS: um alvo fora do ar, os outros medidos e o consolidado dizendo."""
    campanha = Campanha(alvos=(Alvo("https://fora.example", "real pesado"), ALVO),
                        repeticoes=2, pausa_s=10.0)
    chamados: list[str] = []

    def preflight_falso(alvo):
        if alvo.host == "fora.example":
            return False, "ConnectError: name resolution failed"
        return True, "HTTP 200"

    def executar_falso(alvo, destino, base_env=None):
        chamados.append(alvo.host)
        return _summary(ttfb=120.0, total=350.0, fcp=700.0,
                        results=[_r("checks/backend/test_a.py::test_estavel")])

    resultados = rodar(campanha, saida=tmp_path, preflight=preflight_falso,
                       executar=executar_falso, pausar=lambda _s: None, log=lambda *_a: None)

    assert chamados == ["alvo.example", "alvo.example"], (
        "o alvo inacessível não deve consumir execução, o acessível deve rodar as duas")
    dados = _consolidado(resultados)
    assert dados["alvos_acessiveis"] == 1 and dados["alvos_total"] == 2
    fora = next(a for a in dados["alvos"] if a["host"] == "fora.example")
    assert fora["acessivel"] is False and "ConnectError" in fora["motivo"]

    md = render_markdown(dados)
    assert "Alvos inacessíveis" in md and "fora.example" in md
    assert "ConnectError" in md, "o motivo precisa chegar a quem lê o consolidado"


def test_preflight_ok_mas_sem_artefato_vira_inacessivel(tmp_path):
    """Não exibir alvo vazio como se tivesse sido medido."""
    campanha = Campanha(alvos=(ALVO,), repeticoes=2, pausa_s=10.0)
    resultados = rodar(campanha, saida=tmp_path, preflight=lambda _a: (True, "HTTP 200"),
                       executar=lambda *_a, **_k: None, pausar=lambda _s: None,
                       log=lambda *_a: None)
    assert resultados[0].acessivel is False
    assert "nenhuma execução produziu summary.json" in resultados[0].motivo


def test_pausa_minima_respeitada_entre_execucoes(tmp_path):
    """Duas execuções → uma pausa; a primeira não espera por nada."""
    campanha = Campanha(alvos=(ALVO,), repeticoes=3, pausa_s=10.0)
    pausas: list[float] = []
    rodar(campanha, saida=tmp_path, preflight=lambda _a: (True, "HTTP 200"),
          executar=lambda *_a, **_k: _summary(ttfb=1.0, total=2.0, results=[]),
          pausar=pausas.append, log=lambda *_a: None)
    assert pausas == [10.0, 10.0]


# ---------- Guarda passiva ----------

def test_load_authorized_aborta_antes_de_qualquer_requisicao():
    """Caso da OS: campanha é passiva — a guarda vem antes da rede."""
    with pytest.raises(CampanhaAbortada, match="campanha é passiva"):
        verificar_ambiente_passivo({"WEBQA_LOAD_AUTHORIZED": "1"})


def test_guarda_olha_presenca_e_nao_valor():
    """`=0` também aborta: variável pela metade não deve virar surpresa no meio."""
    with pytest.raises(CampanhaAbortada):
        verificar_ambiente_passivo({"WEBQA_LOAD_AUTHORIZED": "0"})
    verificar_ambiente_passivo({})   # ambiente limpo não levanta


def test_main_aborta_sem_tocar_a_rede(monkeypatch):
    import scripts.campanha as campanha_mod

    def nunca(*_a, **_k):
        raise AssertionError("preflight não pode ser chamado com carga autorizada")

    monkeypatch.setattr(campanha_mod, "preflight_http", nunca)
    monkeypatch.setenv("WEBQA_LOAD_AUTHORIZED", "1")
    assert campanha_mod.main([]) == 2


def test_env_da_execucao_isola_saida_e_nunca_propaga_carga(tmp_path):
    destino = tmp_path / "alvo" / "run1"
    env = env_da_execucao(ALVO, destino, {"WEBQA_LOAD_AUTHORIZED": "1", "PATH": "/usr/bin"})
    assert env["WEBQA_REPORT_DIR"] == str(destino)
    assert env["WEBQA_TARGET_URL"] == ALVO.url
    assert env["WEBQA_CRAWL_MAX_PAGES"] == "5"
    assert "WEBQA_LOAD_AUTHORIZED" not in env, "carga jamais é propagada ao pytest"


def test_env_injeta_user_agent_so_quando_o_alvo_declara(tmp_path):
    sem_ua = env_da_execucao(ALVO, tmp_path, {})
    assert "WEBQA_USER_AGENT" not in sem_ua
    com_ua = Alvo("https://wiki.example", "real pesado", 5, "WebQA/1.0 (+contato)")
    assert env_da_execucao(com_ua, tmp_path, {})["WEBQA_USER_AGENT"] == "WebQA/1.0 (+contato)"


# ---------- Consolidado como documento ----------

def test_markdown_tem_as_duas_secoes_de_tempo():
    """Aceite da OS: tempo do ALVO e tempo da SUÍTE, separados."""
    dados = _consolidado([ResultadoAlvo(ALVO, execucoes=_tres_execucoes())])
    md = render_markdown(dados)
    assert "## Tempo do alvo" in md and "## Tempo da suíte" in md
    assert md.index("## Tempo do alvo") < md.index("## Tempo da suíte")
    assert "## Estabilidade do veredito" in md


def test_campanha_sem_nenhum_alvo_acessivel_nao_explode_o_render():
    dados = _consolidado([ResultadoAlvo(ALVO, acessivel=False, motivo="ConnectTimeout")])
    md = render_markdown(dados)
    assert dados["alvos_acessiveis"] == 0
    assert "Nenhum alvo rendeu métrica" in md


# ---------- Erro de fixture: o teste que não aconteceu ----------

def _summary_com_erro():
    """Execução em que o navegador morreu no setup — 2 erros, 1 teste real."""
    return _summary(ttfb=90.0, total=250.0, results=[
        {**_r("checks/frontend/test_rendering.py::test_fcp", "error", dimension="frontend"),
         "fase": "setup", "detail": "Page.goto: net::ERR_CONNECTION_RESET"},
        {**_r("checks/lgpd/test_consentimento.py::test_trackers", "error", dimension="lgpd"),
         "fase": "setup", "detail": "Page.goto: net::ERR_CONNECTION_RESET"},
        {**_r("checks/backend/test_a.py::test_estavel"), "fase": "call"},
    ])


def test_error_e_contado_e_nao_somado_a_failed():
    """`error` é o teste não tendo acontecido — não é veredito sobre o alvo."""
    dims = por_dimensao([_summary_com_erro()])
    assert dims["frontend"]["estados"]["error"]["max"] == 1
    assert dims["frontend"]["estados"]["failed"]["max"] == 0
    assert "error" in render_markdown(
        _consolidado([ResultadoAlvo(ALVO, execucoes=[_summary_com_erro()])]))


def test_teste_com_duas_fases_colapsa_pelo_pior_e_nao_inventa_instabilidade():
    """Call passou e teardown estourou: um desfecho, o pior — não duas amostras."""
    duas_fases = _summary(ttfb=90.0, total=250.0, results=[
        {**_r("checks/lgpd/test_terceiros.py::test_x", "passed"), "fase": "call"},
        {**_r("checks/lgpd/test_terceiros.py::test_x", "error"), "fase": "teardown",
         "detail": "context.close falhou"},
    ])
    assert estados_por_teste(duas_fases) == {"checks/lgpd/test_terceiros.py::test_x": "error"}
    # Três repetições idênticas: nada oscilou, então nada é instável.
    assert instabilidades([duas_fases, duas_fases, duas_fases]) == []


def test_duracao_soma_as_fases_do_mesmo_teste():
    """Setup caro é custo do teste — é onde mora o tempo de levantar navegador."""
    com_setup = _summary(ttfb=1.0, total=2.0, results=[
        {**_r("t::test_x", duration_s=8.0), "fase": "setup"},
        {**_r("t::test_x", duration_s=0.5), "fase": "call"},
    ])
    assert duracoes_por_teste(com_setup) == {"t::test_x": 8.5}
    assert mais_lentos([com_setup])[0]["mediana_s"] == 8.5
