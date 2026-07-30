"""Heurísticas de Nielsen avaliáveis automaticamente.

Cobertura (proxy automatizável) das 10 heurísticas: visibilidade do estado,
correspondência com o mundo real, prevenção de erros, reconhecimento em vez
de memorização, ajuda no erro. Heurísticas subjetivas (estética, flexibilidade)
exigem avaliação humana — registradas em docs/RECOMENDACOES.md.
"""
import pytest

pytestmark = pytest.mark.ux


def test_visibilidade_do_estado_titulo(soup, settings):
    """H1-Nielsen: o título orienta o usuário sobre onde ele está."""
    title = soup.find("title")
    assert title and title.get_text(strip=True), "Sem <title> — usuário não sabe onde está."


def test_identidade_visual_favicon(client, soup, settings):
    icon = soup.find("link", rel=lambda r: r and "icon" in r)
    if icon and icon.get("href"):
        return
    resp = client.get(settings.target_url + "/favicon.ico")
    assert resp.status_code == 200, "Sem favicon — reconhecimento da marca/aba prejudicado."


def test_ajuda_no_erro_pagina_404_amigavel(client, settings, soup):
    """H9-Nielsen: erro deve ajudar o usuário a se recuperar (link de volta)."""
    resp = client.get(settings.target_url + "/webqa-404-ux")
    if resp.status_code not in (404, 410):
        pytest.skip("Alvo não retorna 404 padrão.")
    from bs4 import BeautifulSoup
    err = BeautifulSoup(resp.text, "lxml")
    tem_saida = bool(err.find("a", href=True))
    assert tem_saida, "Página 404 sem nenhum link de saída — usuário fica sem rota de recuperação."


def test_prevencao_de_erros_inputs_tipados(soup):
    """H5-Nielsen: inputs com type/required corretos previnem erro na origem."""
    inputs = soup.find_all("input")
    if not inputs:
        pytest.skip("Página sem inputs.")
    genericos = [
        i for i in inputs
        if i.get("type", "text") == "text"
        and any(k in (i.get("name", "") + i.get("id", "")).lower() for k in ("email", "phone", "tel", "date"))
    ]
    assert not genericos, (
        f"{len(genericos)} campos de e-mail/telefone/data usando type='text' — "
        "perde validação nativa e teclado adequado no mobile."
    )


def test_reconhecimento_links_descritivos(soup):
    """H6-Nielsen: 'clique aqui' obriga o usuário a lembrar contexto."""
    vagos = [
        a.get_text(strip=True) for a in soup.find_all("a")
        if a.get_text(strip=True).lower() in ("clique aqui", "click here", "aqui", "here",
                                              "saiba mais", "read more", "link")
    ]
    proporcao_ok = len(vagos) <= 3
    assert proporcao_ok, f"{len(vagos)} links com texto vago ({set(vagos)}) — prefira rótulos descritivos."


def test_feedback_botoes_de_acao(soup):
    """Formulários precisam de ação clara (botão submit visível)."""
    forms = soup.find_all("form")
    if not forms:
        pytest.skip("Página sem formulários.")
    sem_submit = [
        f.get("action", "?") for f in forms
        if not f.find(["button", "input"], attrs={"type": ["submit", "image"]}) and not f.find("button")
    ]
    assert not sem_submit, f"Formulários sem botão de envio claro: {sem_submit}"
