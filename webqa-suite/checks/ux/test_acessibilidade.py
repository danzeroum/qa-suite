"""Acessibilidade automatizada com axe-core (WCAG) via navegador real.

Foco em risco: violações 'critical' e 'serious' primeiro (limiar em config).
Complementa — não substitui — testes com usuários reais (design centrado
no usuário: empatizar → testar).

Dimensão dupla `ux + lgpd`: no Brasil acessibilidade em site NÃO é só UX, é
obrigação legal — Lei Brasileira de Inclusão (13.146/2015), Art. 63: sítios
devem ser acessíveis ao uso da pessoa com deficiência. Por isso estes testes
contam nas duas dimensões do relatório; o agrupamento fica em `ux` (primeiro
marker declarado), a contagem aparece também em `lgpd`.
"""
import json

import pytest

pytestmark = [pytest.mark.ux, pytest.mark.lgpd, pytest.mark.browser]

# Versão FIXADA + hash SHA-384 verificado antes de injetar (SRI manual):
# CDN comprometido não roda script arbitrário no DOM da página sob teste.
AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"
AXE_SHA384 = ("b91444cffa692592290e122db68c9b6953d29714"
              "bb3457b5b423a41f741597e1f778cd9a2fdd1ad78d32cd829887c4c0")


def _fetch_axe_verified(client) -> str:
    """Baixa o axe-core e valida integridade; falha de hash é ERRO, não skip."""
    import hashlib
    resp = client.get(AXE_CDN)
    resp.raise_for_status()
    digest = hashlib.sha384(resp.content).hexdigest()
    assert digest == AXE_SHA384, (
        f"Integridade do axe-core FALHOU (sha384 {digest[:16]}… != esperado) — "
        "possível comprometimento do CDN; script NÃO foi injetado."
    )
    return resp.text


@pytest.fixture(scope="module")
def axe_results(browser_page, settings, client):
    try:
        axe_js = _fetch_axe_verified(client)
    except AssertionError:
        raise
    except Exception as exc:
        pytest.skip(f"Não foi possível baixar o axe-core ({exc}).")
    browser_page.goto(settings.target_url, wait_until="load", timeout=60_000)
    browser_page.add_script_tag(content=axe_js)
    return browser_page.evaluate("async () => await axe.run()")


def _by_impact(results, impact):
    return [v for v in results["violations"] if v.get("impact") == impact]


def test_sem_violacoes_criticas(axe_results, settings):
    critical = _by_impact(axe_results, "critical")
    resumo = [{"id": v["id"], "help": v["help"], "nodes": len(v["nodes"])} for v in critical]
    assert len(critical) <= settings.threshold("a11y_critical_max"), (
        "Violações WCAG críticas:\n" + json.dumps(resumo, indent=2, ensure_ascii=False)
    )


def test_sem_violacoes_serias(axe_results, settings):
    serious = _by_impact(axe_results, "serious")
    resumo = [{"id": v["id"], "help": v["help"], "nodes": len(v["nodes"])} for v in serious]
    assert len(serious) <= settings.threshold("a11y_serious_max"), (
        "Violações WCAG sérias:\n" + json.dumps(resumo, indent=2, ensure_ascii=False)
    )


def test_imagens_com_alt(soup):
    imgs = soup.find_all("img")
    if not imgs:
        pytest.skip("Sem imagens.")
    sem_alt = [i.get("src", "?")[:80] for i in imgs if i.get("alt") is None]
    assert not sem_alt, f"{len(sem_alt)} imagens sem atributo alt: {sem_alt[:5]}"


def test_inputs_com_rotulo(soup):
    inputs = [i for i in soup.find_all("input") if i.get("type") not in ("hidden", "submit", "button")]
    if not inputs:
        pytest.skip("Sem inputs visíveis.")
    problemas = []
    for i in inputs:
        iid = i.get("id")
        tem_label = bool(iid and soup.find("label", attrs={"for": iid}))
        tem_aria = bool(i.get("aria-label") or i.get("aria-labelledby"))
        dentro_de_label = i.find_parent("label") is not None
        if not (tem_label or tem_aria or dentro_de_label):
            problemas.append(i.get("name") or i.get("id") or "input-sem-nome")
    assert not problemas, f"Inputs sem rótulo acessível: {problemas}"
