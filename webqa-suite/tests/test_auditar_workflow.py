"""VERIFICAÇÃO do workflow reutilizável de auditoria (frente E, E3).

Política executável, não markdown: o contrato de governança do `auditar.yml` é
conferido lendo o próprio YAML. A regra não-negociável (ARQUITETURA §7.2): nenhum
gate de rede (WEBQA_*_AUTHORIZED) vive no ambiente geral — só no passo da Fase C,
guardado pelo opt-in explícito. Assim um consumidor roda o passivo à vontade e a
sondagem ativa só quando alguém, deliberadamente, liga o input e dá o escopo.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.verification

_GATES = ("WEBQA_DISCOVERY_AUTHORIZED", "WEBQA_ACTIVE_PROBES_AUTHORIZED",
          "WEBQA_LOAD_AUTHORIZED")
_YAML = Path(__file__).resolve().parents[2] / ".github/workflows/auditar.yml"


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(_YAML.read_text(encoding="utf-8"))


def _gates_no_env(env: dict | None) -> list[str]:
    return [g for g in _GATES if g in (env or {})]


def test_workflow_existe_e_e_reutilizavel(wf):
    # PyYAML lê `on:` como booleano True (YAML 1.1) — aceite as duas formas.
    gatilho = wf.get("on", wf.get(True))
    assert "workflow_call" in gatilho, "auditar.yml precisa ser workflow_call (reutilizável)"


def test_permissao_e_somente_leitura(wf):
    assert wf["permissions"]["contents"] == "read"


def test_passivo_e_o_padrao_sem_carga(wf):
    gatilho = wf.get("on", wf.get(True))
    default = gatilho["workflow_call"]["inputs"]["dimensoes"]["default"]
    assert "not load" in default          # carga nunca é o padrão


def test_gate_de_rede_nunca_no_ambiente_geral(wf):
    """O invariante §7.2: gate só existe em passo guardado por sondagem_fase_c."""
    job = wf["jobs"]["auditar"]
    assert _gates_no_env(job.get("env")) == []          # nada no nível do job
    for passo in job["steps"]:
        gates = _gates_no_env(passo.get("env"))
        if not gates:
            continue
        guarda = str(passo.get("if", ""))
        assert "sondagem_fase_c" in guarda, (
            f"passo '{passo.get('name')}' expõe {gates} sem o opt-in sondagem_fase_c")


def test_fase_c_exige_o_escopo(wf):
    """A Fase C não roda sem o secret escopo (posse provada por host)."""
    passos = wf["jobs"]["auditar"]["steps"]
    prep = next(p for p in passos if "escopo" in str(p.get("name", "")).lower())
    assert "sondagem_fase_c" in str(prep.get("if", ""))
    assert 'test -n "$ESCOPO"' in prep["run"]           # aborta sem o escopo


def test_entradas_do_consumidor_nao_entram_cru_no_shell(wf):
    """Anti-injeção: target_url/dimensoes chegam por env, nunca ${{ }} em `run:`."""
    for passo in wf["jobs"]["auditar"]["steps"]:
        run = passo.get("run", "")
        assert "${{ inputs.target_url }}" not in run
        assert "${{ inputs.dimensoes }}" not in run
