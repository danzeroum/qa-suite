"""VERIFICAÇÃO: a própria suíte está correta? (nível: unidade)

Separação V&V — estes testes não tocam nenhum alvo externo.
"""
from pathlib import Path

import pytest

from webqa.config import Settings, load_settings

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


def test_config_yaml_carrega_e_tem_thresholds():
    s = load_settings()
    for key in ("ttfb_ms", "p95_ms", "lcp_ms", "cls", "page_weight_kb"):
        assert key in s.thresholds, f"Threshold obrigatório ausente: {key}"


def test_todo_orcamento_de_gui_e_lido_por_algum_check():
    """"A garantia existe, a ligação não" (`PROXIMOS-PASSOS.md §2`), aplicada aos
    limiares.

    Um threshold que ninguém lê é pior que ausente: ele aparece no `config.yaml`,
    alguém o ajusta esperando mudar um veredito, e nada acontece. O defeito não
    tem sintoma — a régua parece configurável e não é.

    A dimensão `gui` chegou a vinte orçamentos em nove OSs, e o risco cresce com a
    contagem. A varredura é textual de propósito: importar os checks aqui exigiria
    Playwright, e a pergunta ("alguém lê esta chave?") não precisa de navegador.
    """
    chaves = {k for k in load_settings().thresholds if k.startswith("gui_")}
    assert chaves, "a dimensão gui perdeu todos os orçamentos — regressão no config.yaml"
    orfaos = _orfaos_entre(chaves)
    assert not orfaos, (
        f"orçamento em config.yaml que nenhum check lê: {orfaos}. "
        "Ajustar um desses não muda veredito nenhum, e quem ajustar não tem como "
        "saber disso — apague a chave ou ligue-a a um assert.")


def test_a_guarda_de_orcamento_orfao_pega_um_plantado():
    """Guarda que não reprova nada é decoração — esta reprova o caso que a motivou."""
    assert _orfaos_entre({"gui_orcamento_que_ninguem_le"}) == ["gui_orcamento_que_ninguem_le"]


def _orfaos_entre(chaves) -> list[str]:
    """As chaves que não aparecem em nenhum arquivo de `checks/`.

    Varredura textual de propósito: importar os checks exigiria Playwright, e a
    pergunta ("alguém lê esta chave?") não precisa de navegador.
    """
    fonte = "\n".join(caminho.read_text(encoding="utf-8")
                      for caminho in sorted((RAIZ / "checks").rglob("*.py")))
    return sorted(chave for chave in chaves if f'"{chave}"' not in fonte)


def test_override_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("WEBQA_TARGET_URL", "https://override.example")
    monkeypatch.setenv("WEBQA_TTFB_MS", "123")
    s = load_settings()
    assert s.target_url == "https://override.example"
    assert s.threshold("ttfb_ms") == 123.0


def test_target_url_sem_barra_final(monkeypatch):
    monkeypatch.setenv("WEBQA_TARGET_URL", "https://x.example/")
    assert load_settings().target_url == "https://x.example"


def test_allowlist_lgpd_default_vazia():
    assert load_settings().lgpd_allowed_third_parties == []


def test_allowlist_lgpd_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("WEBQA_LGPD_ALLOWED_THIRD_PARTIES", "googletagmanager.com, hotjar.com ,")
    assert load_settings().lgpd_allowed_third_parties == ["googletagmanager.com", "hotjar.com"]


def test_settings_e_imutavel():
    s = Settings("u", 1, "ua", 1, True, 1, 1, {"a": 1})
    with pytest.raises((AttributeError, TypeError)):
        s.target_url = "outro"  # type: ignore[misc]
