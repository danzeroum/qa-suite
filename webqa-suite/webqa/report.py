"""Plugin pytest: relatório consolidado de qualidade (JSON + HTML).

Observabilidade aplicada à própria suíte: cada execução deixa um artefato
inspecionável (report/summary.json e report/summary.html) com resultado por
dimensão de qualidade — backend, frontend, ux, functional, acceptance, load, lgpd.

Um teste pode pertencer a MAIS DE UMA dimensão (acessibilidade é UX e é
obrigação legal — LBI, Lei 13.146/2015 Art. 63). Nesse caso ele conta em todas
as dimensões marcadas e é agrupado na primeira declarada.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path

import pytest

from webqa.auth import credencial_do_ambiente
from webqa.dominio import achados_de
from webqa.metricas import coletadas
from webqa.report_html import montar
from webqa.sanitize import mascarar_valores_registrados, safe_url, sanitize_text

DIMENSIONS = (
    "backend", "frontend", "ux", "functional", "acceptance", "load", "lgpd",
    "seguranca", "gui", "verification",
)

# Honestidade epistêmica no CÓDIGO, não só na documentação: quem lê o relatório
# não leu o doc de arquitetura.
DIMENSION_NOTES = {
    "lgpd": (
        "Verificação caixa-preta do que é observável de fora. "
        "Falha PROVA não conformidade; passar NÃO certifica conformidade — "
        "base legal, contrato com operador, ROPA e governança interna não são "
        "observáveis por HTTP."
    ),
    "gui": (
        "Medição da interface renderizada — geometria, CSS computado e tempo de "
        "interação. Falha PROVA um defeito de interface: um alvo de toque de 16px "
        "é pequeno demais em qualquer contexto. Passar NÃO certifica usabilidade — "
        "satisfação, clareza de rótulo, carga cognitiva e uso real com tecnologia "
        "assistiva não se deduzem de geometria conforme."
    ),
}

# Redirecionável por ambiente (12-Factor): o teste de sistema do alvo fixture
# roda um pytest interno, que sobrescreveria o relatório da execução externa.
REPORT_DIR = Path(
    os.environ.get("WEBQA_REPORT_DIR") or Path(__file__).resolve().parent.parent / "report"
)
_RESULTS: list[dict] = []
_START = time.time()

# Desfecho do PREFLIGHT de sessão (conftest.py::alvo_alcancavel). Fica aqui, e não
# no conftest, porque o conftest NÃO viaja no wheel: o laudo é lido por quem
# instalou só a biblioteca, e um sinal que só existisse no repositório seria
# invisível justamente para o consumidor.
#
# Existe porque "o alvo foi alcançado?" é estado de SESSÃO, e não a soma dos
# desfechos. Medido contra uma porta fechada: 58 checks viram `error` (a fixture
# estourou no setup) e 4 viram `failed` (o pytest-bdd faz a requisição DENTRO do
# corpo, então o ConnectError cai na fase `call`). Ler aquela contagem de fora
# produziria "4 violações" — quatro achados sobre um alvo que ninguém alcançou. A
# distinção error/failed do laudo é por FASE, não por natureza, e é por isso que
# ela não basta.
_PREFLIGHT: dict | None = None


def registrar_preflight(alcancado: bool, motivo: str = "") -> None:
    """Registra se o alvo respondeu ao primeiro GET da sessão.

    Chamado pelo preflight (conftest). Idempotente por sessão: o primeiro registro
    vence, porque é o que descreve o estado em que a sessão começou.
    """
    global _PREFLIGHT
    if _PREFLIGHT is None:
        _PREFLIGHT = {"alcancado": bool(alcancado), "motivo": sanitize_text(motivo)[:400]}


def _alvo_observado() -> str:
    """URL do alvo com a query oculta — relatório não reproduz parâmetro do alvo."""
    try:
        from webqa.config import load_settings

        return safe_url(load_settings().target_url)
    except Exception:
        return ""


def _allowlist() -> list[str]:
    """Terceiros liberados pelo controlador — a classificação do inventário respeita."""
    try:
        from webqa.config import load_settings

        return list(load_settings().lgpd_allowed_third_parties)
    except Exception:
        return []


def _comando(session) -> str:
    """Comando da execução, para o relatório dizer como reproduzir a si mesmo."""
    try:
        args = " ".join(session.config.invocation_params.args)
    except Exception:
        args = ""
    # Sanitizado como qualquer outro texto que vai a disco: era o único campo do
    # laudo que chegava ao arquivo sem passar por nada, e argv aceita URL com
    # `?token=` como argumento tanto quanto uma mensagem de erro.
    return sanitize_text(f"pytest {args}".strip())


def _catalog_hash() -> str:
    """Digest da lista curada aplicada — a régua carimbada (E4, cláusula 4).

    Reaproveita `webqa.sondagem.hash_dos_caminhos`: uma segunda implementação
    derivaria, e o primeiro dia em que as duas discordassem seria o dia em que dois
    laudos "0 achados" pareceriam da mesma régua sem serem.

    Lista ausente vira `"UNAVAILABLE"`, nunca vazio nem zero: o consumidor precisa
    distinguir "não usei catálogo" de "usei este catálogo", e uma string vazia
    passaria por qualquer comparação de igualdade com outra string vazia.
    """
    try:
        from webqa.sondagem import hash_dos_caminhos

        return hash_dos_caminhos(Path(__file__).resolve().parent.parent
                                 / "data" / "caminhos-sensiveis.yaml")
    except (OSError, ImportError):
        return "UNAVAILABLE"


def _commit_do_padrao() -> str:
    """Commit da RÉGUA, não do projeto consumidor. Mesma leitura de webqa/sondagem."""
    try:
        from webqa.sondagem import _commit_do_padrao as commit

        return commit() or "UNAVAILABLE"
    except ImportError:
        return "UNAVAILABLE"


def report_dir() -> Path:
    """Diretório de artefatos, criado sob demanda (usado também pelos checks)."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return REPORT_DIR


def pytest_configure(config):
    """Resolve a credencial UMA vez, antes da coleta, e assim a registra.

    Aqui, e não numa fixture, porque construir a `Credencial` é o que a torna
    mascarável — e uma execução só de navegador (`-m "lgpd and browser"`) nunca
    constrói o cliente HTTP. Amarrar o registro ao cliente deixaria a varredura
    vazia justamente na execução em que o Chromium autenticou.

    Registro e varredura moram no mesmo módulo de propósito: a sincronia entre os
    dois vira invariante local em vez de acoplamento a distância.

    Configuração pela metade aborta AQUI, antes de qualquer requisição — a
    mensagem nomeia a variável que falta e nunca cita valor.
    """
    try:
        credencial_do_ambiente()
    except ValueError as erro:
        pytest.exit(str(erro), returncode=4)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Anexa ao report as dimensões NA ORDEM EM QUE FORAM DECLARADAS.

    `report.keywords` é um conjunto sem ordem confiável; a ordem de declaração é
    o que define quem "vence" o agrupamento de um teste multidimensional.
    Também marca se o teste exige navegador — insumo do ledger de estabilidade
    (scripts/estabilidade.py), que só olha para a dimensão browser.
    """
    outcome = yield
    result = outcome.get_result()
    result.webqa_dimensions = [m.name for m in item.iter_markers() if m.name in DIMENSIONS]
    result.webqa_browser = any(m.name == "browser" for m in item.iter_markers())


def pytest_runtest_logreport(report):
    # ERRO de setup/teardown também entra. Antes, só `call` e skip de setup eram
    # registrados — e uma fixture que estourava levava o teste inteiro a
    # DESAPARECER do relatório. Não era perda cosmética: numa execução em que o
    # Chromium não alcançava o alvo, 13 desfechos sumiam, o ledger de
    # estabilidade não achava assinatura de infra nenhuma para classificar e
    # dava a noite como LIMPA — inflando exatamente a métrica que existe para
    # provar que a infraestrutura de navegador funciona.
    interessa = (
        report.when == "call"
        or (report.when == "setup" and (report.skipped or report.failed))
        or (report.when == "teardown" and report.failed)
    )
    if not interessa:
        return
    dims = getattr(report, "webqa_dimensions", None)
    if not dims:  # fallback: sem o hookwrapper (ex.: report sintético)
        dims = [m for m in DIMENSIONS if m in report.keywords]
    # `detail` também para skip: o MOTIVO do skip distingue "sem imagens na
    # página" (resultado legítimo) de "Chromium indisponível" (falha de infra).
    # Sem isso não há como separar flake de veredito — sempre sanitizado.
    detalhe = (
        sanitize_text(str(report.longrepr))[:800]
        if (report.failed or report.skipped)
        else ""
    )
    # `outcome` fica VERBATIM do pytest (o classificador do ledger depende dele).
    # `estado` é a leitura visual: xfail é estado próprio, não um skip qualquer —
    # sem isso o relatório contaria alerta como pulado e perderia a distinção que
    # a dimensão lgpd inteira usa (obrigação × sinal de maturidade).
    # `error` é a terceira distinção: falha FORA do corpo do teste não é veredito
    # sobre o alvo, é o teste não tendo acontecido.
    if report.failed and report.when != "call":
        estado = "error"
    elif hasattr(report, "wasxfail"):
        estado = "xfail"
    else:
        estado = report.outcome
    _RESULTS.append(
        {
            "test": report.nodeid,
            "dimension": dims[0] if dims else "other",
            "dimensions": dims or ["other"],
            "browser": bool(getattr(report, "webqa_browser", "browser" in report.keywords)),
            "outcome": report.outcome,
            "estado": estado,
            # A fase distingue "falhou medindo" de "nem chegou a medir". Um teste
            # pode render duas entradas (call passou, teardown estourou); quem
            # conta desfecho por teste colapsa pelo pior — ver
            # scripts/campanha.py::estados_por_teste.
            "fase": report.when,
            "duration_s": round(getattr(report, "duration", 0.0), 3),
            "detail": detalhe,
            **_metadados_de_seguranca(report.nodeid),
        }
    )


def _metadados_de_seguranca(nodeid: str) -> dict:
    """`severidade`, `fase_seguranca` e `remediacao` quando o teste produziu Findings.

    Campos OPCIONAIS: dimensões anteriores não os têm, e o template não pode
    exigi-los — um summary antigo tem de renderizar exatamente como antes.
    A severidade reportada é a PIOR do teste: um teste que achou uma chave AWS e
    um token nomeado é um achado de severidade alta, não uma média das duas.

    `remediacao` acompanha o achado mais severo e só entra quando existe —
    achados A/B costumam não ter, e uma chave vazia poluiria o schema antigo.
    """
    achados = achados_de(nodeid)
    if not achados:
        return {}
    meta = {"severidade": achados[0].severidade, "fase_seguranca": achados[0].fase}
    if achados[0].remediacao:
        meta["remediacao"] = achados[0].remediacao
    # `procedencia` (OWASP/CWE) acompanha o achado quando existe; ausente, a
    # chave nem aparece — mesmo contrato retrocompatível de `remediacao`.
    if achados[0].procedencia:
        meta["procedencia"] = achados[0].procedencia
    return meta


def pytest_sessionfinish(session, exitstatus):
    out_dir = report_dir()

    by_dim: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for r in _RESULTS:
        for dim in r.get("dimensions") or [r["dimension"]]:
            by_dim[dim][r["outcome"]] = by_dim[dim].get(r["outcome"], 0) + 1

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.time() - _START, 1),
        "alvo": _alvo_observado(),
        "comando": _comando(session),
        "by_dimension": by_dim,
        "dimension_notes": DIMENSION_NOTES,
        # Medidas do ALVO (webqa/metricas.py), não vereditos: TTFB, total, FCP,
        # LCP, CLS. Ficam só no JSON — o summary.html segue o contrato visual
        # congelado na OS-15, e acrescentar seção ali é iteração de DESIGN, não
        # de instrumentação. Métrica ausente é chave ausente, nunca zero.
        "metricas": coletadas(),
        "results": _RESULTS,
    }
    if _PREFLIGHT is not None:
        summary["preflight"] = _PREFLIGHT
    # O VEREDITO, carimbado no laudo pela MESMA função que decide o código de saída
    # de `webqa-veredicto` (webqa/veredito.py). Um só lugar decide: se o laudo e o
    # exit fossem calculados em dois lugares, a primeira divergência entre eles
    # seria justamente a que ninguém veria — e o par exit/laudo é a única coisa que
    # um consumidor consegue auditar sem ler o log.
    #
    # ADITIVO: `results`, `by_dimension`, `metricas` e todo o resto seguem
    # exatamente como estavam. Um summary antigo continua renderizando, e um
    # consumidor em transição continua lendo o que já lia.
    from webqa.veredito import avaliar

    veredito = avaliar(summary)
    summary["veredito"] = {
        "estado": veredito.estado,
        "motivo": veredito.motivo,
        "codigo_de_saida": veredito.codigo,
    }
    # Booleano à parte, e não derivado na leitura: `inconclusivo` é o campo que o
    # consumidor usa para NÃO tratar "não medi" como "medi e passou", e exigir que
    # ele reimplemente a conta seria devolver a inferência que a origem acabou de
    # assumir.
    summary["inconclusivo"] = veredito.inconclusivo

    # FINGERPRINT (E4): os cinco campos que dizem com o que este laudo é
    # comparável. Sem eles, dois laudos parecem comparáveis sem serem, e a
    # diferença entre um "0 achados" e outro deixa de significar o que se pensa
    # que significa — catálogo encurtado em segredo produz exatamente isso.
    from webqa.laudo import fingerprint

    summary["fingerprint"] = fingerprint(_catalog_hash(), _commit_do_padrao())
    # A varredura por VALOR acontece sobre a string SERIALIZADA, não sobre o
    # dicionário — e é isso que a torna estrutural. Campo novo que alguém
    # acrescente ao `summary` amanhã já nasce coberto; chave conta tanto quanto
    # valor; e o que entra pelo `montar` sem passar por `summary` (inventário de
    # terceiros, allowlist) também. As formas escapadas registradas em
    # `auth.variantes_da_senha` são o que faz isso valer apesar do escape de JSON
    # e do `html.escape` do template.
    (out_dir / "summary.json").write_text(
        mascarar_valores_registrados(json.dumps(summary, indent=2, ensure_ascii=False)),
        encoding="utf-8",
    )

    # O ENVELOPE DO CONTRATO (E4), em arquivo IRMÃO e não dentro do summary.
    #
    # O envelope fecha o objeto com `unevaluatedProperties: false`: fazer o summary
    # validar contra ele exigiria apagar `results`, `by_dimension` e `metricas` —
    # quebrar todo consumidor em transição para satisfazer um schema. Os dois
    # formatos respondem a perguntas diferentes, e é por isso que são dois arquivos:
    # o summary é a MEDIÇÃO, o laudo é o VEREDITO com procedência.
    #
    # Mesma borda de escrita do summary: a varredura por valor acontece sobre a
    # string SERIALIZADA, então o envelope nasce coberto sem precisar saber disso.
    from webqa.laudo import montar as montar_laudo

    (out_dir / "laudo.json").write_text(
        mascarar_valores_registrados(
            json.dumps(montar_laudo(summary, catalog_hash=summary["fingerprint"]["catalog_hash"],
                                    commit=summary["fingerprint"]["commit"]),
                       indent=2, ensure_ascii=False)),
        encoding="utf-8",
    )

    # HTML conforme o pacote de design liberado pelo gate (OS-14): a montagem
    # vive em webqa/report_html.py, testável sem pytest e sem navegador.
    inventario = None
    caminho_terceiros = out_dir / "terceiros.json"
    if caminho_terceiros.exists():
        try:
            inventario = json.loads(caminho_terceiros.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            inventario = None   # inventário ilegível não derruba o relatório

    (out_dir / "summary.html").write_text(
        mascarar_valores_registrados(montar(summary, inventario, _allowlist())),
        encoding="utf-8",
    )
