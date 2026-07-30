"""VERIFICAÇÃO: o ledger de estabilidade conta o que diz contar.

A métrica só vale se separar flake de infra de veredito sobre o alvo — se
errar, ou trava a Fase 2 para sempre, ou a destrava sem estabilidade real.
Summaries fabricados em tmp_path; nenhuma rede, nenhum navegador.
"""
import json
from pathlib import Path

import pytest

from scripts.estabilidade import (
    ORIGEM_OFICIAL,
    _dia_utc_de,
    carregar_ledger,
    classificar,
    main,
    origem_da_execucao,
    registrar,
    sequencia_oficial,
    sha256_do_alvo,
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

def _entrada(dia, *, origem=ORIGEM_OFICIAL, flakes=0, alvo=SHA, quando=None, browser=9):
    return {
        "generated_at": quando or f"{dia} 03:17:00",
        "dia_utc": dia,
        "origem": origem,
        "alvo_sha256": alvo,
        "browser_total": browser,
        "infra_flakes": flakes,
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
    """A entrada pré-migração não tem dia_utc; veio de runner em UTC."""
    antiga = {"generated_at": "2026-07-30 02:38:18", "origem": ORIGEM_OFICIAL,
              "alvo_sha256": SHA, "browser_total": 9, "infra_flakes": 0}
    assert sequencia_oficial([antiga, _entrada("2026-07-31")]) == (2, 2)


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
