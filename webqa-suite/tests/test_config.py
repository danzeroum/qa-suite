"""VERIFICAÇÃO: a própria suíte está correta? (nível: unidade)

Separação V&V — estes testes não tocam nenhum alvo externo.
"""
import pytest

from webqa.config import Settings, load_settings

pytestmark = pytest.mark.verification


def test_config_yaml_carrega_e_tem_thresholds():
    s = load_settings()
    for key in ("ttfb_ms", "p95_ms", "lcp_ms", "cls", "page_weight_kb"):
        assert key in s.thresholds, f"Threshold obrigatório ausente: {key}"


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
