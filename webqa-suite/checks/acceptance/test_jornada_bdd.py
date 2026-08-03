"""Validação de aceitação em BDD (pytest-bdd): a jornada básica do visitante.

Amplia a aceitação para além do smoke (C4). Cada cenário compõe o que a suíte já
mede de forma PASSIVA (um GET, como um visitante faria) numa necessidade do
usuário — idioma legível, conteúdo real, erro tratado com clareza. Nada aqui
adivinha rota nem lê corpo além do que o navegador comum baixaria.
"""
import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.acceptance

scenarios("features/jornada.feature")

# Caminho deliberadamente inexistente: estável entre execuções (não aleatório,
# para o resultado ser reproduzível) e claramente não uma rota real. UM só GET —
# checar como o serviço trata "não encontrado" é acessível a qualquer visitante,
# não é sondagem (que é lista curada, gated, Fase C).
_CAMINHO_INEXISTENTE = "/webqa-endereco-que-nao-existe-verificacao-de-404"


@pytest.fixture()
def ctx():
    return {}


@given("que o serviço está publicado")
def servico_publicado(settings, ctx):
    ctx["base"] = settings.target_url


@when("o visitante acessa a página inicial")
def acessa_home(client, ctx):
    ctx["resp"] = client.get(ctx["base"])
    ctx["soup"] = BeautifulSoup(ctx["resp"].text, "lxml")


@when("o visitante acessa um endereço que não existe")
def acessa_inexistente(client, ctx):
    alvo = ctx["base"].rstrip("/") + _CAMINHO_INEXISTENTE
    ctx["resp"] = client.get(alvo)


@then("a página declara o idioma do seu conteúdo")
def declara_idioma(ctx):
    html = ctx["soup"].find("html")
    lang = (html.get("lang") if html else "") or ""
    assert lang.strip(), (
        "A página não declara `lang` no <html> — leitor de tela e tradução do "
        "navegador ficam sem saber o idioma do conteúdo.")


@then("a página apresenta um conteúdo principal com texto")
def tem_conteudo(ctx):
    soup = ctx["soup"]
    marco = soup.find("main") or soup.find("h1")
    assert marco is not None, "Sem <main> nem <h1>: a página não tem conteúdo principal claro."
    texto = soup.get_text(" ", strip=True)
    assert len(texto) >= 20, (
        f"A página inicial traz quase nenhum texto ({len(texto)} chars) — casca "
        "vazia ou conteúdo que só aparece via JavaScript.")


@then('o serviço responde claramente "não encontrado"')
def responde_nao_encontrado(ctx):
    assert ctx["resp"].status_code == 404, (
        f"Endereço inexistente respondeu {ctx['resp'].status_code}, não 404. "
        "O visitante que erra o endereço merece um 'não encontrado' claro.")


@then("não devolve um erro de servidor nem finge que a página existe")
def nem_5xx_nem_soft_200(ctx):
    status = ctx["resp"].status_code
    assert status < 500, f"Endereço inexistente derrubou o servidor ({status})."
    assert not (200 <= status < 300), (
        f"Endereço inexistente respondeu {status} (2xx): soft-404 mascara o erro e "
        "confunde o visitante — 'não encontrado' tem de ser um 404 honesto.")
