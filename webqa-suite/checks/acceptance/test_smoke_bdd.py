"""Validação de aceitação em BDD (pytest-bdd): Given/When/Then executável."""
import pytest
from bs4 import BeautifulSoup
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.acceptance

scenarios("features/smoke.feature")


@pytest.fixture()
def ctx():
    return {}


@given("que o serviço está publicado")
def servico_publicado(settings, ctx):
    ctx["url"] = settings.target_url


@when("o visitante acessa a página inicial")
def acessa_home(client, ctx):
    from webqa.http_utils import timed_get
    ctx["timing"] = timed_get(client, ctx["url"])
    ctx["resp"] = client.get(ctx["url"])


@then("a resposta chega com sucesso em tempo aceitável")
def resposta_ok(ctx, settings):
    assert 200 <= ctx["timing"].status < 300
    assert ctx["timing"].total_ms <= settings.threshold("p95_ms"), (
        f"Página inicial levou {ctx['timing'].total_ms:.0f}ms"
    )


@then("a página possui um título que orienta o visitante")
def titulo_orienta(ctx):
    soup = BeautifulSoup(ctx["resp"].text, "lxml")
    ctx["soup"] = soup
    title = soup.find("title")
    assert title and len(title.get_text(strip=True)) >= 5


@then("a página oferece navegação para outras áreas")
def possui_navegacao(ctx):
    soup = ctx["soup"]
    assert soup.find("a", href=True), "Nenhum link encontrado na página inicial."
