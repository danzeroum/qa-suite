"""VERIFICAÇÃO: o ledger de estabilidade conta o que diz contar.

A métrica só vale se separar flake de infra de veredito sobre o alvo — se
errar, ou trava a Fase 2 para sempre, ou a destrava sem estabilidade real.
Summaries fabricados em tmp_path; nenhuma rede, nenhum navegador.
"""
import json

import pytest

from scripts.estabilidade import (
    carregar_ledger,
    classificar,
    main,
    registrar,
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


def _aplicar(ledger, summary):
    return registrar(ledger, classificar(summary), SHA)


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
                      sha256_do_alvo("https://outro.com"))
    assert outro.alvo_mudou and outro.streak == 1


def test_ledger_nunca_guarda_a_url_em_claro():
    ledger = {"schema": 1, "execucoes": []}
    _aplicar(ledger, _limpo("2026-01-01 10:00:00"))
    serializado = json.dumps(ledger)
    assert "alvo.com" not in serializado and "https://" not in serializado
    assert ledger["execucoes"][0]["alvo_sha256"] == SHA


# ---------- CLI ----------

def test_rodar_duas_vezes_no_mesmo_summary_gera_uma_entrada(tmp_path, capsys):
    summary = _escrever(tmp_path, "summary.json", _limpo("2026-01-01 10:00:00"))
    ledger = tmp_path / "ledger.json"
    argv = [str(summary), "--ledger", str(ledger), "--alvo", ALVO]

    assert main(argv) == 0
    assert main(argv) == 0
    assert "já registrada" in capsys.readouterr().out
    assert len(carregar_ledger(ledger)["execucoes"]) == 1


def test_streak_de_dez_destrava_a_fase_2(tmp_path, capsys):
    ledger = tmp_path / "ledger.json"
    for dia in range(1, 11):
        summary = _escrever(tmp_path, f"s{dia}.json", _limpo(f"2026-01-{dia:02d} 10:00:00"))
        assert main([str(summary), "--ledger", str(ledger), "--alvo", ALVO]) == 0
    saida = capsys.readouterr().out
    assert "FASE 2 DESTRAVADA" in saida and "10/10" in saida


def test_dry_run_nao_grava(tmp_path, capsys):
    summary = _escrever(tmp_path, "summary.json", _limpo("2026-01-01 10:00:00"))
    ledger = tmp_path / "ledger.json"
    assert main([str(summary), "--ledger", str(ledger), "--alvo", ALVO, "--dry-run"]) == 0
    assert not ledger.exists()
    assert "dry-run" in capsys.readouterr().out


def test_summary_ausente_falha_com_instrucao(tmp_path, capsys):
    codigo = main([str(tmp_path / "nao-existe.json"), "--ledger", str(tmp_path / "l.json"),
                   "--alvo", ALVO])
    assert codigo == 2
    assert "rode a suíte antes" in capsys.readouterr().err
