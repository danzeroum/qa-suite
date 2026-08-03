"""VERIFICAÇÃO do ciclo de vida do achado contra baseline.yaml (C2 fatia 2)."""
from __future__ import annotations

import pytest

from webqa.baseline import (
    CORRIGIDO,
    PERSISTENTE,
    carregar_baseline,
    chave,
    classificar,
)
from webqa.dominio import Finding

pytestmark = pytest.mark.verification


def _f(recurso, tipo="exposicao:vcs"):
    return Finding(tipo, recurso, "alta", "presente", "C", remediacao="corrija")


def test_novo_reprova_o_pipeline():
    ciclo = classificar([_f("https://a/.git/HEAD")], baseline={})
    assert [chave(f) for f in ciclo.novos] == ["exposicao:vcs|https://a/.git/HEAD"]
    assert ciclo.reprova is True


def test_persistente_e_silenciado_nao_reprova():
    f = _f("https://a/.git/HEAD")
    ciclo = classificar([f], baseline={chave(f): PERSISTENTE})
    assert ciclo.persistentes == (f,) and ciclo.novos == ()
    assert ciclo.reprova is False


def test_reaberto_reprova_como_regressao():
    f = _f("https://a/.git/HEAD")
    ciclo = classificar([f], baseline={chave(f): CORRIGIDO})   # marcado corrigido, voltou
    assert ciclo.reabertos == (f,)
    assert ciclo.reprova is True


def test_desaparecido_vira_possivel_correcao_e_nao_e_removido():
    """Persistente no baseline, ausente no run → 'possível correção', revisão
    manual. NUNCA some do baseline automaticamente (a memória se preserva)."""
    baseline = {"exposicao:vcs|https://a/.git/HEAD": PERSISTENTE}
    ciclo = classificar([], baseline=baseline)     # run vazio
    assert ciclo.desaparecidos == ("exposicao:vcs|https://a/.git/HEAD",)
    assert ciclo.reprova is False
    # o classificador não muta o baseline (não remove nada)
    assert baseline == {"exposicao:vcs|https://a/.git/HEAD": PERSISTENTE}


def test_carregar_baseline_ausente_e_vazio(tmp_path):
    assert carregar_baseline(tmp_path / "nao-existe.yaml") == {}


def test_carregar_baseline_le_chave_e_estado(tmp_path):
    p = tmp_path / "baseline.yaml"
    p.write_text(
        "achados:\n"
        '  - chave: "exposicao:vcs|https://a/.git/HEAD"\n'
        '    estado: "persistente"\n',
        encoding="utf-8")
    assert carregar_baseline(p) == {"exposicao:vcs|https://a/.git/HEAD": PERSISTENTE}


def test_mix_novo_persistente_e_desaparecido():
    velho = _f("https://a/.git/HEAD")
    novo = _f("https://a/.env", tipo="exposicao:configuracao")
    baseline = {chave(velho): PERSISTENTE,
                "exposicao:backup|https://a/backup.zip": PERSISTENTE}
    ciclo = classificar([velho, novo], baseline=baseline)
    assert ciclo.persistentes == (velho,)
    assert ciclo.novos == (novo,)
    assert ciclo.desaparecidos == ("exposicao:backup|https://a/backup.zip",)
    assert ciclo.reprova is True     # por causa do novo
