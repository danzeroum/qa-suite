"""Envelope de laudo do Contrato de Régua — ADITIVO sobre o summary que já existe.

**O que o consumidor não tinha.** O laudo emitido era `schema_version: 1.0` e não
carregava `verdict`. O consumidor então INFERIA — `ci/suite_runner.py::
traduzir_veredito` — e inferência não é laudo: quem mede é quem sabe. Faltava
também o *fingerprint*: sem `(name, version, commit, catalog_hash,
schema_version)`, dois laudos não são comparáveis e a diferença entre eles não
significa nada. Hashes divergentes na MESMA versão significam catálogo editado,
que é precisamente o que a cláusula existe para revelar.

**Aditivo, e a palavra é literal.** Nada do `summary.json` muda de forma: ele
ganha `fingerprint`, e o envelope do contrato sai num arquivo IRMÃO
(`report/laudo.json`). A alternativa — reformar o summary para caber no schema —
exigiria apagar `results`, `by_dimension` e `metricas`, porque o envelope fecha o
objeto com `unevaluatedProperties: false`. Seria quebrar todo consumidor em
transição para satisfazer um schema, quando os dois formatos respondem a perguntas
diferentes: o summary é a MEDIÇÃO, o envelope é o VEREDITO com procedência.

**O que NUNCA vira achado.** `xfailed` e `skipped`. xfail é desfecho por ambiente
(origem declarada, engine instalada, tempo); skip é não-avaliado. Exportá-los
transformaria *"não afirmei"* em *"defeito medido"* — a mentira mais cara que um
laudo pode contar, porque tem a forma de uma evidência. `error` também não vira
achado: é o teste não tendo acontecido, e o que ele produz é `inconclusivo`.

**A nota epistêmica viaja junto.** `notas` carrega as mesmas advertências que o
summary já publica por dimensão (`DIMENSION_NOTES`): falha PROVA não conformidade;
passar NÃO certifica. Um envelope que só levasse o veredito faria o consumidor ler
`conforme` sem a ressalva que a régua sempre fez questão de imprimir.

**Sanitize na borda de ESCRITA.** Este módulo monta o dicionário; quem escreve é
`webqa/report.py`, que passa a string serializada por `mascarar_valores_registrados`
— a mesma borda de sempre, e por isso o envelope nasce coberto sem precisar saber
disso.
"""
from __future__ import annotations

import os

from webqa import __version__

# Versão do envelope que EXIGE `verdict` (report.schema.json do contrato). Fixa
# aqui e conferida contra o schema pinado em `contrato/contract-v1/`: declarar 1.3
# é o que obriga o campo, e emitir o campo é o que obriga a declaração — o schema
# trava as duas direções, e um número solto aqui poderia mentir sobre as duas.
SCHEMA_VERSION = "1.3"

# Tradução dos três estados internos para o vocabulário do contrato. Um dicionário
# e não `if`s: o mapa é a coisa a revisar, e ele cabe em cinco linhas.
VEREDITO_PARA_CONTRATO = {
    "sem_violacao_observada": ("conforme", "ok"),
    "violacao": ("nao_conforme", "findings"),
    "indeterminado": ("inconclusivo", "error"),
    "config_invalida": ("inconclusivo", "error"),
}

NOTA_EPISTEMICA = (
    "Verificação caixa-preta do que é observável de fora. Falha PROVA não conformidade; "
    "passar NÃO certifica conformidade — exit 0 significa 'nenhuma violação observada', "
    "nunca 'conforme'."
)


def fingerprint(catalog_hash: str, commit: str) -> dict:
    """Os cinco campos que dizem COM O QUE este laudo é comparável.

    `catalog_hash` é o nome geral do que a procedência desta suíte chama de
    `sensitive_paths_hash`: a lista curada de uma régua de QA é um catálogo entre
    outros, e o contrato nomeia a categoria, não o caso.
    """
    return {
        "name": "webqa-suite",
        "version": __version__,
        "commit": commit,
        "catalog_hash": catalog_hash,
        "schema_version": SCHEMA_VERSION,
    }


def _achados(summary: dict) -> list[dict]:
    """Um achado por check que REPROVOU medindo o alvo — e só.

    `estado == "failed"` e nada mais. A tentação de incluir `error` (parece falha)
    e `xfail` (parece defeito conhecido) é exatamente o que a doutrina recusa: erro
    é o teste não tendo acontecido, xfail é ambiente, skip é não-avaliado. Nenhum
    dos três é veredito sobre o alvo, e exportá-los daria ao consumidor um número
    de achados que ninguém mediu.
    """
    achados = []
    for r in summary.get("results") or []:
        if r.get("estado") != "failed":
            continue
        achado = {
            "id": r.get("test", ""),
            "severity": r.get("severidade") or "medium",
            "dimension": r.get("dimension") or "other",
        }
        if r.get("detail"):
            achado["summary"] = r["detail"][:400]
        achados.append(achado)
    return achados


def _execucao(summary: dict, modo: str, runner_kind: str) -> dict:
    """O bloco `execution`. `network_used` é EVIDÊNCIA do modo, não declaração.

    Toda dimensão desta suíte mede um alvo por HTTP; o único modo sem rede é o
    inventário, que não passa por aqui. Derivar da presença de alvo observado, e
    não de um parâmetro, é o que impede um chamador de declarar "sem rede" numa
    execução que tocou o alvo.
    """
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID") or summary.get("generated_at", ""),
        "mode": modo,
        "network_used": bool(summary.get("alvo")),
        "active_gates": sorted(
            nome for nome, var in (("discovery", "WEBQA_DISCOVERY_AUTHORIZED"),
                                   ("active_probes", "WEBQA_ACTIVE_PROBES_AUTHORIZED"),
                                   ("load", "WEBQA_LOAD_AUTHORIZED"))
            if os.environ.get(var)),
        "runner_kind": runner_kind,
    }


def montar(summary: dict, *, catalog_hash: str, commit: str,
           modo: str = "passive", runner_kind: str = "ci") -> dict:
    """O envelope do contrato a partir do summary já montado.

    Função pura sobre o summary: é o que permite fabricá-lo nos três estados sem
    rodar a suíte, inclusive nas bordas que não dá para produzir de verdade.
    """
    estado = (summary.get("veredito") or {}).get("estado", "indeterminado")
    veredito, resultado = VEREDITO_PARA_CONTRATO.get(estado, ("inconclusivo", "error"))
    achados = _achados(summary)
    fp = fingerprint(catalog_hash, commit)

    # `result` é derivado do que se OBSERVOU, e não do rótulo: um veredito
    # `nao_conforme` sem achado nenhum seria incoerente, e o schema do contrato
    # recusa `conforme` com result != ok justamente para que a trava valha contra
    # o gesto deliberado e não só contra o descuido.
    if veredito == "nao_conforme":
        resultado = "findings" if achados else "error"

    return {
        "schema_version": SCHEMA_VERSION,
        "standard": {
            "name": fp["name"],
            "version": fp["version"],
            "commit": fp["commit"],
            "sensitive_paths_hash": fp["catalog_hash"],
        },
        "consumer_project": {
            "repository": os.environ.get("GITHUB_REPOSITORY", "local"),
            "commit": os.environ.get("GITHUB_SHA", "unknown"),
        },
        "execution": _execucao(summary, modo, runner_kind),
        "result": resultado,
        "verdict": veredito,
        "verdict_reason": (summary.get("veredito") or {}).get("motivo") or NOTA_EPISTEMICA,
        "findings": achados,
        "summary": {
            "por_estado": _por_estado(summary),
            "inconclusivo": bool(summary.get("inconclusivo")),
            "nota_epistemica": NOTA_EPISTEMICA,
            "notas_por_dimensao": summary.get("dimension_notes") or {},
        },
    }


def _por_estado(summary: dict) -> dict[str, int]:
    """Contagem por estado — a MEDIDA, que registra sempre.

    Medida não é veredito: `skipped` e `xfail` aparecem aqui porque aconteceram, e
    não aparecem em `findings` porque não são achado. Ausência nunca vira zero: um
    estado que não ocorreu simplesmente não tem chave.
    """
    contagem: dict[str, int] = {}
    for r in summary.get("results") or []:
        estado = r.get("estado") or r.get("outcome") or "?"
        contagem[estado] = contagem.get(estado, 0) + 1
    return contagem
