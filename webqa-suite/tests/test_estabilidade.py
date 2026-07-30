"""VERIFICAÇÃO: o ledger de estabilidade conta o que diz contar.

A métrica só vale se separar flake de infra de veredito sobre o alvo — se
errar, ou trava a Fase 2 para sempre, ou a destrava sem estabilidade real.
Summaries fabricados em tmp_path; nenhuma rede, nenhum navegador.
"""
import json
from pathlib import Path

import pytest

from scripts.estabilidade import (
    CLASSIFICADOR_VERSAO,
    DEFEITOS_CONHECIDOS,
    ORIGEM_OFICIAL,
    SCHEMA,
    _dia_utc_de,
    carregar_ledger,
    classificar,
    em_quarentena,
    main,
    origem_da_execucao,
    quarentena,
    registrar,
    sequencia_oficial,
    sha256_do_alvo,
    versao_de,
)

pytestmark = pytest.mark.verification

ALVO = "https://alvo.com"
SHA = sha256_do_alvo(ALVO)


# ---------- Fábricas de summary ----------

def _result(test, *, browser=True, outcome="passed", detail=""):
    return {
        "test": test,
        "dimension": "lgpd",
        "dimensions": ["lgpd"],
        "browser": browser,
        "outcome": outcome,
        "duration_s": 0.1,
        "detail": detail,
    }


def _summary(quando, results):
    return {"generated_at": quando, "results": results}


def _limpo(quando):
    return _summary(quando, [_result("checks/lgpd/test_consentimento.py::test_x")])


def _com_timeout(quando):
    return _summary(quando, [
        _result("checks/lgpd/test_consentimento.py::test_x"),
        _result("checks/lgpd/test_terceiros.py::test_y", outcome="failed",
                detail="playwright._impl._errors.TimeoutError: Page.goto: Timeout 60000ms exceeded"),
    ])


def _escrever(tmp_path, nome, summary):
    caminho = tmp_path / nome
    caminho.write_text(json.dumps(summary), encoding="utf-8")
    return caminho


def _aplicar(ledger, summary, origem=ORIGEM_OFICIAL):
    """Aplica como se fosse execução do ambiente oficial (a origem é o que move
    a métrica; ver a emenda de arquitetura em docs/LGPD.md)."""
    return registrar(ledger, classificar(summary), SHA, origem=origem)


# ---------- Aceite ----------

def test_duas_execucoes_limpas_e_um_timeout():
    ledger = {"schema": 1, "execucoes": []}
    assert _aplicar(ledger, _limpo("2026-01-01 10:00:00")).streak == 1
    assert _aplicar(ledger, _limpo("2026-01-02 10:00:00")).streak == 2
    assert _aplicar(ledger, _com_timeout("2026-01-03 10:00:00")).streak == 0
    assert [e["infra_flakes"] for e in ledger["execucoes"]] == [0, 0, 1]


def test_fail_deterministico_nao_zera_a_sequencia():
    """Tracker antes do consentimento é veredito sobre o alvo, não flake."""
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-01-01 10:00:00"))
    reprovacao = _summary("2026-01-02 10:00:00", [
        _result("checks/lgpd/test_consentimento.py::test_sem_trackers", outcome="failed",
                detail="AssertionError: 1 rastreador(es) dispararam ANTES de qualquer "
                       "consentimento (LGPD Art. 7º I): ['www.googletagmanager.com']"),
    ])
    assert _aplicar(ledger, reprovacao).streak == 2


def test_timeout_s_no_cabecalho_de_fixtures_nao_e_flake():
    """Regressão: o pytest imprime `Settings(..., timeout_s=15.0, ...)` no
    longrepr de QUALQUER falha. Casar "timeout" sem caixa fazia toda reprovação
    determinística virar flake, e a sequência nunca sairia de zero."""
    ledger = {"schema": 1, "execucoes": []}
    ruido = _summary("2026-01-01 10:00:00", [
        _result("checks/lgpd/test_terceiros.py::test_sri", outcome="failed",
                detail="settings = Settings(target_url='https://alvo.com', timeout_s=15.0, "
                       "user_agent='WebQA-Suite/1.0')\nE  AssertionError: 1 script sem SRI"),
    ])
    registro = _aplicar(ledger, ruido)
    assert registro.streak == 1 and ledger["execucoes"][0]["infra_flakes"] == 0


def test_skip_por_navegador_ausente_e_flake():
    ledger = {"schema": 1, "execucoes": []}
    ausente = _summary("2026-01-01 10:00:00", [
        _result("checks/ux/test_acessibilidade.py::test_a", outcome="skipped",
                detail="Chromium indisponível: rode `python -m playwright install chromium`"),
    ])
    assert _aplicar(ledger, ausente).streak == 0


def test_skip_legitimo_nao_e_flake():
    """'Sem imagens' é resultado do alvo, não defeito do ambiente."""
    ledger = {"schema": 1, "execucoes": []}
    legitimo = _summary("2026-01-01 10:00:00", [
        _result("checks/ux/test_acessibilidade.py::test_imagens", outcome="skipped",
                detail="Skipped: Sem imagens."),
    ])
    assert _aplicar(ledger, legitimo).streak == 1


def test_execucao_sem_browser_e_ignorada():
    """Não conta e não zera — não diz nada sobre o network_log."""
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-01-01 10:00:00"))
    so_http = _summary("2026-01-02 10:00:00", [
        _result("checks/lgpd/test_transparencia.py::test_politica", browser=False),
    ])
    registro = _aplicar(ledger, so_http)
    assert registro.ignorada and registro.streak == 1
    assert len(ledger["execucoes"]) == 1  # nada foi appendado

    # e a execução seguinte continua de onde parou
    assert _aplicar(ledger, _limpo("2026-01-03 10:00:00")).streak == 2


def test_troca_de_alvo_reinicia_a_sequencia():
    """Sequência é por alvo: misturar alvos produziria um número sem sentido."""
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-01-01 10:00:00"))
    outro = registrar(ledger, classificar(_limpo("2026-01-02 10:00:00")),
                      sha256_do_alvo("https://outro.com"), origem=ORIGEM_OFICIAL)
    assert outro.alvo_mudou and outro.streak == 1


def test_ledger_nunca_guarda_a_url_em_claro():
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-01-01 10:00:00"))
    serializado = json.dumps(ledger)
    assert "alvo.com" not in serializado and "https://" not in serializado
    assert ledger["execucoes"][0]["alvo_sha256"] == SHA


# ---------- CLI ----------

def test_rodar_duas_vezes_no_mesmo_summary_gera_uma_entrada(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WEBQA_ORIGEM", ORIGEM_OFICIAL)
    summary = _escrever(tmp_path, "summary.json", _limpo("2026-01-01 10:00:00"))
    ledger = tmp_path / "ledger.json"
    argv = [str(summary), "--ledger", str(ledger), "--alvo", ALVO]

    assert main(argv) == 0
    assert main(argv) == 0
    assert "já registrada" in capsys.readouterr().out
    assert len(carregar_ledger(ledger)["execucoes"]) == 1


def test_streak_de_dez_destrava_a_fase_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WEBQA_ORIGEM", ORIGEM_OFICIAL)   # dez dias UTC distintos
    ledger = tmp_path / "ledger.json"
    for dia in range(1, 11):
        summary = _escrever(tmp_path, f"s{dia}.json", _limpo(f"2026-01-{dia:02d} 10:00:00"))
        assert main([str(summary), "--ledger", str(ledger), "--alvo", ALVO]) == 0
    saida = capsys.readouterr().out
    assert "FASE 2 DESTRAVADA" in saida
    assert f"streak 10/10 ({ORIGEM_OFICIAL}, 10 dias distintos)" in saida


def test_dry_run_nao_grava(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("WEBQA_ORIGEM", ORIGEM_OFICIAL)
    summary = _escrever(tmp_path, "summary.json", _limpo("2026-01-01 10:00:00"))
    ledger = tmp_path / "ledger.json"
    assert main([str(summary), "--ledger", str(ledger), "--alvo", ALVO, "--dry-run"]) == 0
    assert not ledger.exists()
    assert "dry-run" in capsys.readouterr().out


# ---------- Origem: só CI move a métrica ----------

def _entrada(dia, *, origem=ORIGEM_OFICIAL, flakes=0, alvo=SHA, quando=None, browser=9,
             versao=CLASSIFICADOR_VERSAO):
    """Entrada de ledger COMO ELA EXISTE depois da migração.

    `classificador` explícito porque estas fábricas montam o histórico em
    memória, sem passar por carregar_ledger (que é quem migra). Entrada sem o
    campo é, por definição, v1 — e v1 está em quarentena, o que mascararia os
    testes de origem e de dia com um motivo que não é o deles.
    """
    return {
        "generated_at": quando or f"{dia} 03:17:00",
        "dia_utc": dia,
        "origem": origem,
        "alvo_sha256": alvo,
        "browser_total": browser,
        "infra_flakes": flakes,
        "classificador": versao,
    }


def test_entrada_local_entre_duas_oficiais_nao_avanca_nem_zera():
    """Execução em ambiente não oficial não é evidência de estabilidade."""
    historico = [
        _entrada("2026-08-01"),
        _entrada("2026-08-01", origem="local", flakes=4),
        _entrada("2026-08-02"),
    ]
    assert sequencia_oficial(historico) == (2, 2)


def test_flake_em_entrada_local_nao_derruba_a_sequencia_oficial():
    historico = [_entrada("2026-08-01"), _entrada("2026-08-02", origem="local", flakes=7)]
    assert sequencia_oficial(historico) == (1, 1)


def test_duas_execucoes_oficiais_no_mesmo_dia_contam_uma():
    """Noturno + dispatch manual no mesmo dia UTC não inflam a métrica."""
    historico = [
        _entrada("2026-08-01", quando="2026-08-01 03:17:00"),
        _entrada("2026-08-01", quando="2026-08-01 14:02:00"),
    ]
    assert sequencia_oficial(historico) == (1, 1)


def test_vale_a_primeira_do_dia():
    """Primeira limpa e segunda com flake: o dia conta como limpo."""
    historico = [_entrada("2026-08-01"), _entrada("2026-08-01", flakes=3)]
    assert sequencia_oficial(historico) == (1, 1)


def test_virada_de_dia_utc_conta_dois_dias():
    historico = [
        _entrada("2026-08-01", quando="2026-08-01 23:59:00"),
        _entrada("2026-08-02", quando="2026-08-02 00:01:00"),
    ]
    assert sequencia_oficial(historico) == (2, 2)


def test_ledger_misto_conta_so_o_ambiente_oficial():
    """Histórico 'ci' + noites 'vps': a conta é só das vps, e apagar o
    histórico não muda o número (ele não contamina nem sustenta a métrica)."""
    historico_ci = [
        _entrada("2026-07-29", origem="ci"),
        _entrada("2026-07-30", origem="ci"),
    ]
    noites_vps = [_entrada("2026-08-01"), _entrada("2026-08-02")]
    misto = [*historico_ci, *noites_vps]
    assert sequencia_oficial(misto) == (2, 2)
    assert sequencia_oficial(noites_vps) == sequencia_oficial(misto)


def test_flake_na_ultima_noite_vps_zera_apesar_do_historico_ci_limpo():
    misto = [_entrada("2026-07-30", origem="ci"), _entrada("2026-08-01", flakes=2)]
    assert sequencia_oficial(misto) == (0, 1)


def test_entrada_sem_campo_origem_e_tratada_como_local():
    """Ausência do campo significa procedência desconhecida — não conta."""
    orfa = _entrada("2026-08-02")
    del orfa["origem"]
    assert sequencia_oficial([_entrada("2026-08-01"), orfa]) == (1, 1)


def test_flake_oficial_zera_e_dia_seguinte_recomeca():
    historico = [
        _entrada("2026-08-01"), _entrada("2026-08-02"),
        _entrada("2026-08-03", flakes=1), _entrada("2026-08-04"),
    ]
    assert sequencia_oficial(historico) == (1, 4)


def test_troca_de_alvo_entre_dias_oficiais_reinicia():
    historico = [
        _entrada("2026-08-01"), _entrada("2026-08-02"),
        _entrada("2026-08-03", alvo="outro-digest"),
    ]
    assert sequencia_oficial(historico) == (1, 3)


def test_dia_utc_ausente_cai_para_o_prefixo_de_generated_at():
    """A entrada pré-migração não tem dia_utc; veio de runner em UTC.

    `classificador` explícito para isolar o que este teste mede: sem ele a
    entrada cairia na quarentena da v1 e o resultado falaria de versão, não do
    fallback de dia. A interação das duas regras é coberta em
    test_entrada_sem_versao_cai_na_quarentena_mesmo_sem_dia_utc.
    """
    antiga = {"generated_at": "2026-07-30 02:38:18", "origem": ORIGEM_OFICIAL,
              "alvo_sha256": SHA, "browser_total": 9, "infra_flakes": 0,
              "classificador": CLASSIFICADOR_VERSAO}
    assert sequencia_oficial([antiga, _entrada("2026-07-31")]) == (2, 2)


def test_entrada_sem_versao_cai_na_quarentena_mesmo_sem_dia_utc():
    """As duas regras juntas: a entrada legada é pré-campo, logo v1, logo fora.

    É exatamente o formato da única entrada do ledger real.
    """
    antiga = {"generated_at": "2026-07-30 02:38:18", "origem": ORIGEM_OFICIAL,
              "alvo_sha256": SHA, "browser_total": 9, "infra_flakes": 0}
    assert sequencia_oficial([antiga, _entrada("2026-07-31")]) == (1, 1)


def test_github_actions_nao_declara_mais_origem(monkeypatch):
    """Regressão da emenda: estar no runner do GitHub não basta — o ambiente
    oficial é o container da VPS, e a origem é declarada, não detectada."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("WEBQA_ORIGEM", raising=False)
    assert origem_da_execucao() == "local"


def test_registrar_grava_origem_e_dia_utc(monkeypatch):
    monkeypatch.setenv("WEBQA_ORIGEM", ORIGEM_OFICIAL)
    ledger = {"schema": 2, "execucoes": []}
    registro = registrar(ledger, classificar(_limpo("2026-08-01 03:17:00")), SHA,
                         dia_utc="2026-08-01")
    assert registro.origem == ORIGEM_OFICIAL and registro.streak == 1 and registro.dias == 1
    assert ledger["execucoes"][0]["origem"] == ORIGEM_OFICIAL
    assert ledger["execucoes"][0]["dia_utc"] == "2026-08-01"


def test_registrar_local_nao_move_a_sequencia(monkeypatch):
    monkeypatch.delenv("WEBQA_ORIGEM", raising=False)
    ledger = {"schema": 2, "execucoes": [_entrada("2026-08-01")]}
    registro = registrar(ledger, classificar(_com_timeout("2026-08-02 10:00:00")), SHA,
                         dia_utc="2026-08-02")
    assert registro.origem == "local"
    assert registro.streak == 1, "flake local não pode zerar a sequência oficial"
    assert ledger["execucoes"][-1]["streak"] == 1


# ---------- VALIDAÇÃO: o ledger real do repositório ----------

def _ledger_real() -> dict:
    caminho = Path(__file__).resolve().parent.parent / "docs" / "lgpd-estabilidade.json"
    if not caminho.exists():
        pytest.skip("ledger ainda não existe no repositório")
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_ledger_real_declara_origem_em_toda_entrada():
    """Sem o campo, a entrada deixa de contar — e a regressão seria silenciosa."""
    execucoes = _ledger_real()["execucoes"]
    sem_origem = [e.get("generated_at", "?") for e in execucoes if "origem" not in e]
    assert not sem_origem, f"entradas sem origem no ledger versionado: {sem_origem}"
    invalidas = [e["origem"] for e in execucoes if e["origem"] not in ("vps", "ci", "local")]
    assert not invalidas, f"origens fora do vocabulário: {invalidas}"


def test_ledger_real_recomputa_a_sequencia_oficial():
    """A sequência recalculada é a verdade; o campo `streak` de entradas
    anteriores à emenda foi gravado sob a regra antiga e é só histórico."""
    execucoes = _ledger_real()["execucoes"]
    streak, dias = sequencia_oficial(execucoes)
    oficiais = [e for e in execucoes if e.get("origem") == ORIGEM_OFICIAL]
    assert dias == len({_dia_utc_de(e) for e in oficiais})
    assert streak <= dias
    if not oficiais:
        assert streak == 0, (
            "sem nenhuma execução do ambiente oficial a sequência tem de ser 0 — "
            "a emenda reiniciou a contagem, e entradas 'ci' são histórico"
        )


def test_remover_a_entrada_ci_historica_nao_altera_a_sequencia():
    """Prova que o histórico não contamina a conta: com ou sem ele, o mesmo número."""
    execucoes = _ledger_real()["execucoes"]
    sem_historico = [e for e in execucoes if e.get("origem") != "ci"]
    assert sequencia_oficial(execucoes) == sequencia_oficial(sem_historico)


def test_summary_padrao_segue_webqa_report_dir(tmp_path, monkeypatch):
    """Regressão: a suíte ESCREVE em WEBQA_REPORT_DIR; ler de um caminho fixo
    fazia o noturno do container classificar summary velho — ou nenhum, já que
    a imagem não carrega `report/`."""
    monkeypatch.setenv("WEBQA_REPORT_DIR", str(tmp_path / "relatorio"))
    import importlib

    import scripts.estabilidade as mod
    recarregado = importlib.reload(mod)
    try:
        assert recarregado.SUMMARY_PADRAO == tmp_path / "relatorio" / "summary.json"
    finally:
        monkeypatch.delenv("WEBQA_REPORT_DIR", raising=False)
        importlib.reload(mod)


def test_summary_ausente_falha_com_instrucao(tmp_path, capsys):
    codigo = main([str(tmp_path / "nao-existe.json"), "--ledger", str(tmp_path / "l.json"),
                   "--alvo", ALVO])
    assert codigo == 2
    assert "rode a suíte antes" in capsys.readouterr().err


# ---------- Regressão: navegador morto não é noite limpa ----------

def test_erro_de_setup_do_navegador_nao_conta_como_noite_limpa():
    """Regressão encontrada pela campanha (nível sistema).

    Numa execução em que o Chromium não alcançava o alvo, os testes estouravam no
    SETUP das fixtures. Como webqa/report.py registrava apenas a fase `call`,
    esses desfechos desapareciam do summary: sobravam dois skips, nenhuma
    assinatura de infra para casar, e a noite entrava no ledger como LIMPA —
    inflando justamente a métrica que existe para provar que a infraestrutura de
    navegador funciona. Com a fase registrada, `net::` aparece e zera a sequência.
    """
    summary = _summary("2026-07-30 04:00:00", [
        _result("checks/frontend/test_rendering.py::test_fcp", outcome="failed",
                detail="playwright._impl._errors.Error: Page.goto: "
                       "net::ERR_CONNECTION_RESET at https://alvo.example/"),
        _result("checks/lgpd/test_consentimento.py::test_x", outcome="failed",
                detail="playwright._impl._errors.Error: Page.goto: "
                       "net::ERR_CONNECTION_RESET at https://alvo.example/"),
    ])
    classificacao = classificar(summary)
    assert classificacao.browser_total == 2
    assert len(classificacao.flakes) == 2, "net:: é assinatura de infra, não veredito"
    assert classificacao.limpa is False, "navegador inalcançável jamais é noite limpa"


def test_sequencia_zera_quando_o_navegador_esta_inalcancavel():
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-07-28 04:00:00"))
    _aplicar(ledger, _limpo("2026-07-29 04:00:00"))
    morto = _summary("2026-07-30 04:00:00", [
        _result("checks/frontend/test_rendering.py::test_fcp", outcome="failed",
                detail="Page.goto: net::ERR_CONNECTION_RESET"),
    ])
    registro = _aplicar(ledger, morto)
    assert registro.streak == 0, "duas noites boas não sobrevivem a um navegador morto"


# ---------- OS-18: versão do classificador e quarentena ----------

def test_entrada_nova_carimba_a_versao_do_classificador():
    ledger = {"schema": SCHEMA, "execucoes": []}
    registro = _aplicar(ledger, _limpo("2026-08-01 04:00:00"))
    assert registro.entrada["classificador"] == CLASSIFICADOR_VERSAO


def test_migracao_one_shot_marca_entrada_sem_campo_como_v1(tmp_path):
    """Ausência do campo é anterior à sua criação — logo v1, nunca a versão atual.

    Assumir a corrente daria fé de integridade a exatamente o dado que não a tem.
    """
    caminho = tmp_path / "ledger.json"
    caminho.write_text(json.dumps({"schema": 2, "execucoes": [
        {"generated_at": "2026-07-30 02:38:18", "origem": "ci", "alvo_sha256": SHA,
         "browser_total": 9, "infra_flakes": 0, "streak": 1}]}), encoding="utf-8")
    ledger = carregar_ledger(caminho)
    assert ledger["execucoes"][0]["classificador"] == 1
    assert versao_de(ledger["execucoes"][0]) == 1
    assert em_quarentena(ledger["execucoes"][0])


def test_v1_limpa_nao_conta_e_nao_zera():
    """Quarentena: nem avança (veredito não confiável) nem derruba (pode ter sido boa)."""
    execucoes = [_entrada("2026-08-01", versao=1),
                 _entrada("2026-08-02", versao=1)]
    assert sequencia_oficial(execucoes) == (0, 0), "v1 não conta"

    execucoes = [_entrada("2026-08-01", versao=1),
                 _entrada("2026-08-02", versao=2),
                 _entrada("2026-08-03", versao=1)]
    streak, dias = sequencia_oficial(execucoes)
    assert (streak, dias) == (1, 1), "só a v2 conta, e a v1 posterior não a zera"


def test_v1_com_flake_tambem_fica_em_quarentena_e_nao_zera_a_v2():
    """v1 SUJA também é ignorada: o juiz que a condenou é o mesmo que errava."""
    execucoes = [_entrada("2026-08-01", versao=2),
                 _entrada("2026-08-02", versao=1, flakes=3),
                 _entrada("2026-08-03", versao=2)]
    assert sequencia_oficial(execucoes) == (2, 2)


def test_v1_no_mesmo_dia_de_v2_nao_rouba_a_vaga_do_dia():
    """Regressão do desenho: filtrar a quarentena ANTES do agrupamento por dia."""
    execucoes = [_entrada("2026-08-01", versao=1),
                 {**_entrada("2026-08-01", versao=2),
                  "generated_at": "2026-08-01 05:00:00"}]
    assert sequencia_oficial(execucoes) == (1, 1)


def test_versao_futura_desconhecida_conta_normalmente():
    """Defeito é lista FECHADA de culpados, não whitelist.

    Travar a sequência para sempre porque um refactor esqueceu de registrar a
    versão seria um fail-safe que falha para o lado errado.
    """
    assert 3 not in DEFEITOS_CONHECIDOS
    execucoes = [_entrada("2026-08-01", versao=3),
                 _entrada("2026-08-02", versao=99)]
    assert sequencia_oficial(execucoes) == (2, 2)


def test_nove_v1_limpas_mais_correcao_recomecam_sem_apagar_historico():
    """Simulação da OS: 9 noites boas julgadas pelo juiz defeituoso + a correção."""
    execucoes = [_entrada(f"2026-08-{dia:02d}", versao=1) for dia in range(1, 10)]
    assert sequencia_oficial(execucoes) == (0, 0), "nove v1 não valem nada para a meta"

    execucoes.append(_entrada("2026-08-10", versao=2))
    streak, _dias = sequencia_oficial(execucoes)
    assert streak == 1, "a contagem RECOMEÇA em 1, não continua de 9"
    assert len(execucoes) == 10, "e nada foi apagado — histórico auditável"


def test_quarentena_reporta_contagem_por_versao():
    execucoes = [_entrada("2026-08-01", versao=1),
                 _entrada("2026-08-02", versao=1),
                 _entrada("2026-08-03", versao=2)]
    assert quarentena(execucoes) == {1: 2}


def test_saida_explica_a_quarentena_e_o_recomeco(tmp_path, capsys):
    """Sem o motivo à vista, '0/10' depois de nove noites parece bug do script."""
    caminho = tmp_path / "ledger.json"
    caminho.write_text(json.dumps({"schema": 4, "execucoes": [
        _entrada("2026-08-01", versao=1)]}), encoding="utf-8")
    assert main(["--ledger", str(caminho), "--recompute"]) == 0
    saida = capsys.readouterr().out
    assert "streak 0/10" in saida
    assert "quarentena: v1 (1 entrada)" in saida
    assert DEFEITOS_CONHECIDOS[1] in saida
    assert "RECOMEÇA do zero, sem apagar o histórico" in saida


def test_recompute_do_ledger_real_nao_grava_nada(tmp_path, capsys):
    """Auditoria é leitura: recompute não pode alterar o ledger."""
    caminho = tmp_path / "ledger.json"
    original = json.dumps({"schema": 2, "execucoes": [
        {"generated_at": "2026-07-30 02:38:18", "origem": "ci", "alvo_sha256": SHA,
         "browser_total": 9, "infra_flakes": 0, "streak": 1}]})
    caminho.write_text(original, encoding="utf-8")
    assert main(["--ledger", str(caminho), "--recompute"]) == 0
    assert caminho.read_text(encoding="utf-8") == original, "recompute não escreve"
    saida = capsys.readouterr().out
    assert "streak 0/10" in saida and "quarentena: v1" in saida
