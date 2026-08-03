"""VERIFICAÇÃO da correlação de achados (C3b). Puro sobre Finding, sem rede."""
from __future__ import annotations

import pytest

from webqa.correlacao import correlacionar_findings
from webqa.dominio import Finding

pytestmark = pytest.mark.verification


def _f(recurso, categoria, sev="alta"):
    return Finding(f"exposicao:{categoria}", recurso, sev, "presente", "C",
                   remediacao="corrija")


def test_git_e_env_no_mesmo_host_vira_uma_anotacao():
    findings = [_f("https://a.exemplo/.git/HEAD", "vcs"),
                _f("https://a.exemplo/.env", "configuracao")]
    anot = correlacionar_findings(findings)
    assert len(anot) == 1
    assert anot[0]["host"] == "a.exemplo"
    assert anot[0]["tipo"] == "risco-composto:codigo-fonte-e-segredos"
    assert set(anot[0]["componentes"]) == {"https://a.exemplo/.git/HEAD", "https://a.exemplo/.env"}


def test_host_so_com_env_nao_gera_anotacao():
    assert correlacionar_findings([_f("https://a.exemplo/.env", "configuracao")]) == []


def test_git_e_env_em_hosts_diferentes_nao_correlaciona():
    findings = [_f("https://a.exemplo/.git/HEAD", "vcs"),
                _f("https://b.exemplo/.env", "configuracao")]
    assert correlacionar_findings(findings) == []


def test_nao_altera_severidade_nem_cria_finding():
    """A anotação é agrupamento: não muda severidade dos findings nem carrega uma."""
    findings = [_f("https://a.exemplo/.git/HEAD", "vcs", sev="media"),
                _f("https://a.exemplo/.env", "configuracao", sev="alta")]
    anot = correlacionar_findings(findings)
    # severidades individuais intactas
    assert [f.severidade for f in findings] == ["media", "alta"]
    # a anotação NÃO tem campo de severidade (não é Finding, não escala risco)
    assert "severidade" not in anot[0]


def test_dois_hosts_com_combo_geram_duas_anotacoes_ordenadas():
    findings = [_f("https://b.exemplo/.git/HEAD", "vcs"),
                _f("https://b.exemplo/.env", "configuracao"),
                _f("https://a.exemplo/.git/HEAD", "vcs"),
                _f("https://a.exemplo/.env", "configuracao")]
    anot = correlacionar_findings(findings)
    assert [a["host"] for a in anot] == ["a.exemplo", "b.exemplo"]   # determinístico
