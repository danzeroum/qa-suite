"""VERIFICAÇÃO de que cada derivador está LIGADO ao template (OS-34).

Fecha um furo que a suíte tinha e não via: **teste verde sobre função morta.**

No #31, `motivos_do_zero()` tinha testes de derivação passando enquanto o bloco
**não estava interpolado** no `montar`. A função calculava certo, os testes
conferiam o retorno, a suíte ficava verde — e a página saía sem os três motivos.
É a mesma família do D6, em que o `quality-gate` ficava verde sem exercer o
contrato do alvo: a garantia existia, a ligação não.

A estratégia aqui é mecânica em vez de manual. Cada derivador é substituído por
uma **sentinela** e a página inteira é renderizada: se a sentinela não aparece no
HTML final, aquela interpolação sumiu do template. Um teste por derivador, e a
lista é explícita de propósito — enumerar direto do template faria a cobertura
encolher junto com a interpolação removida, que é exatamente o que se quer pegar.

Isto é validação, não verificação: os testes de cada gerador continuam checando
o CONTEÚDO derivado. O que se prova aqui é que ele chega à página.
"""
from __future__ import annotations

import pytest

from webqa import estabilidade_html, report_html

pytestmark = pytest.mark.verification

# Derivadores de cada gerador. Lista EXPLÍCITA: se fosse extraída do template,
# remover a interpolação removeria também o teste que a cobre — o furo se
# fecharia sozinho no papel e continuaria aberto na página.
DERIVADORES_SUMMARY = (
    "_cabecalho", "_avisos", "_panorama", "_achados", "_alertas",
    "_erros", "_terceiros", "_tabela", "_rodape",
)
DERIVADORES_PAINEL = ("_historia", "_slots", "_bloco_do_zero", "_nota_de_alvo", "_tabela")

SENTINELA = "<!--DERIVADOR-LIGADO-{nome}-->"


def _summary_completo() -> dict:
    """Summary que aciona TODOS os ramos do template, inclusive os condicionais.

    `_erros` só é interpolado quando há `error` — sem uma entrada de infra, o
    teste daquele derivador passaria por nunca ter sido exercido, que é
    precisamente o engano que este arquivo existe para impedir.
    """
    def r(test, estado, dimension="lgpd", fase="call", **extra):
        return {"test": test, "dimension": dimension, "dimensions": [dimension],
                "browser": True, "outcome": estado, "estado": estado, "fase": fase,
                "duration_s": 0.2, "detail": f"detalhe de {test}", **extra}

    return {
        "generated_at": "2026-07-30 03:00:00",
        "alvo": "http://127.0.0.1:8000",
        "duration_s": 12.3,
        "comando": "pytest -m lgpd",
        "by_dimension": {"lgpd": {"passed": 1, "failed": 1, "skipped": 0}},
        "dimension_notes": {"lgpd": "falhar prova não conformidade"},
        "metricas": {"ttfb_ms": 90.0},
        "results": [
            r("checks/lgpd/a.py::ok", "passed"),
            r("checks/lgpd/b.py::achado", "failed", severidade="alta", fase_seguranca="A"),
            r("checks/lgpd/c.py::alerta", "xfail"),
            r("checks/lgpd/d.py::pulado", "skipped"),
            r("checks/ux/e.py::infra", "error", dimension="ux", fase="setup"),
        ],
    }


def _ledger_completo() -> dict:
    """Ledger que aciona os quatro derivadores do painel de uma vez.

    Dois `alvo_sha256` para a nota de troca de alvo, e a sequência terminando em
    zero para o bloco de motivos.
    """
    def noite(dia, origem="vps", sha="a" * 64, flakes=0):
        return {"generated_at": f"{dia} 03:14:00", "dia_utc": dia, "origem": origem,
                "alvo_sha256": sha, "browser_total": 7, "infra_flakes": flakes,
                "classificador": 2}

    return {"schema": 5, "execucoes": [
        noite("2026-08-01"),
        noite("2026-08-02", sha="b" * 64),
        noite("2026-08-03", sha="b" * 64, flakes=1),
    ]}


def _renderizar_summary() -> str:
    return report_html.montar(_summary_completo(), {"hosts": {}}, [])


def _renderizar_painel() -> str:
    from scripts.estabilidade import caminhada

    ledger = _ledger_completo()
    return estabilidade_html.montar(ledger, caminhada(ledger["execucoes"]), 11,
                                    sha_do_alvo_atual="c" * 64)


# ---------- o inventário fecha ----------

def test_lista_do_summary_cobre_tudo_que_o_template_interpola():
    """Derivador novo tem de entrar na lista, senão nasce sem esta cobertura."""
    import inspect
    import re

    corpo = inspect.getsource(report_html.montar)
    interpolados = set(re.findall(r"\{(_[a-z_]+)\(", corpo))
    faltando = sorted(interpolados - set(DERIVADORES_SUMMARY))
    assert not faltando, (
        f"o template interpola {faltando} e a lista desta suíte não os cobre — "
        "acrescente-os a DERIVADORES_SUMMARY.")


def test_lista_do_painel_cobre_tudo_que_o_template_interpola():
    import inspect
    import re

    corpo = inspect.getsource(estabilidade_html.montar)
    interpolados = {n for n in re.findall(r"\{(_[a-z_]+)\(", corpo)
                    if n not in ("_sha_curto",)}     # usado fora do corpo do doc
    faltando = sorted(interpolados - set(DERIVADORES_PAINEL))
    assert not faltando, (
        f"o template interpola {faltando} e a lista desta suíte não os cobre — "
        "acrescente-os a DERIVADORES_PAINEL.")


# ---------- cada derivador é portante ----------

@pytest.mark.parametrize("nome", DERIVADORES_SUMMARY)
def test_derivador_do_summary_chega_ao_html(monkeypatch, nome):
    """Substituído por sentinela, ele TEM de aparecer na página renderizada.

    Se não aparecer, a interpolação saiu do template e o derivador virou função
    morta — com todos os seus testes de retorno continuando verdes.
    """
    marca = SENTINELA.format(nome=nome)
    monkeypatch.setattr(report_html, nome, lambda *a, **k: marca)

    assert marca in _renderizar_summary(), (
        f"{nome}() não é interpolado por report_html.montar — a função deriva "
        "conteúdo que nunca chega ao summary.html.")


@pytest.mark.parametrize("nome", DERIVADORES_PAINEL)
def test_derivador_do_painel_chega_ao_html(monkeypatch, nome):
    marca = SENTINELA.format(nome=nome)
    monkeypatch.setattr(estabilidade_html, nome, lambda *a, **k: marca)

    assert marca in _renderizar_painel(), (
        f"{nome}() não é interpolado por estabilidade_html.montar — a função "
        "deriva conteúdo que nunca chega ao estabilidade.html.")


# ---------- vazio legítimo × não interpolado ----------

def test_vazio_legitimo_nao_se_confunde_com_nao_interpolado():
    """A distinção que o teste de retorno sozinho não consegue fazer.

    `_bloco_do_zero` devolve `""` quando a sequência está viva — vazio legítimo,
    e a página segue válida. Isso é indistinguível, no HTML, de a interpolação
    ter sumido. A sentinela separa os dois: com a função substituída, o slot
    aparece mesmo quando o conteúdo real seria vazio.
    """
    from scripts.estabilidade import caminhada

    # Sequência viva: o bloco de motivos legitimamente não tem o que dizer.
    vivas = {"schema": 5, "execucoes": [
        {"generated_at": f"2026-08-0{d} 03:14:00", "dia_utc": f"2026-08-0{d}",
         "origem": "vps", "alvo_sha256": "a" * 64, "browser_total": 7,
         "infra_flakes": 0, "classificador": 2} for d in (1, 2)]}
    passos = caminhada(vivas["execucoes"])

    real = estabilidade_html.montar(vivas, passos, 11, sha_do_alvo_atual="a" * 64)
    assert "Por que a contagem está em zero" not in real, "vazio legítimo"
    assert real.count("<h1") == 1, "a página segue válida com o bloco vazio"


def test_slot_do_bloco_existe_mesmo_quando_o_conteudo_e_vazio(monkeypatch):
    """Complemento do teste acima: o slot está lá, só não tem o que mostrar."""
    from scripts.estabilidade import caminhada

    vivas = {"schema": 5, "execucoes": [
        {"generated_at": "2026-08-01 03:14:00", "dia_utc": "2026-08-01",
         "origem": "vps", "alvo_sha256": "a" * 64, "browser_total": 7,
         "infra_flakes": 0, "classificador": 2}]}
    marca = SENTINELA.format(nome="_bloco_do_zero")
    monkeypatch.setattr(estabilidade_html, "_bloco_do_zero", lambda *a, **k: marca)

    html = estabilidade_html.montar(vivas, caminhada(vivas["execucoes"]), 11,
                                    sha_do_alvo_atual="a" * 64)
    assert marca in html, "o slot sumiu do template — não é vazio, é ausência"


def test_laudo_sem_achados_mantem_os_derivadores_ligados(monkeypatch):
    """Laudo 100% verde: `_achados` devolve seção vazia, mas continua interpolado."""
    verde = _summary_completo()
    verde["results"] = [r for r in verde["results"] if r["estado"] == "passed"]

    marca = SENTINELA.format(nome="_achados")
    monkeypatch.setattr(report_html, "_achados", lambda *a, **k: marca)
    assert marca in report_html.montar(verde, None, [])
