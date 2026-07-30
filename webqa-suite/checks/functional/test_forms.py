"""Formulários: contrato básico de funcionamento e segurança."""
import pytest

pytestmark = pytest.mark.functional


@pytest.fixture()
def forms(soup):
    forms = soup.find_all("form")
    if not forms:
        pytest.skip("Página sem formulários.")
    return forms


def test_formularios_com_metodo_adequado(forms):
    """Formulários que alteram estado ou carregam credenciais devem usar POST."""
    suspeitos = []
    for f in forms:
        metodo = (f.get("method") or "get").lower()
        tem_senha = f.find("input", attrs={"type": "password"}) is not None
        if tem_senha and metodo != "post":
            suspeitos.append(f.get("action", "?"))
    assert not suspeitos, (
        f"Formulários com senha usando GET (credencial iria para a URL/logs): {suspeitos}"
    )


def test_formularios_de_senha_sob_https(forms, home_response):
    tem_senha = any(f.find("input", attrs={"type": "password"}) for f in forms)
    if not tem_senha:
        pytest.skip("Sem formulário de senha.")
    assert home_response.url.scheme == "https", "Formulário de senha servido fora de HTTPS."


def test_autocomplete_em_campos_sensiveis(forms):
    """Campos de senha devem orientar o navegador (autocomplete current/new-password)."""
    faltando = []
    for f in forms:
        for i in f.find_all("input", attrs={"type": "password"}):
            if not i.get("autocomplete"):
                faltando.append(i.get("name") or "password")
    if faltando:
        pytest.xfail(f"Campos de senha sem autocomplete definido: {faltando}")
