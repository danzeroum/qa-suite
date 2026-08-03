"""Correlação de achados da Fase C — risco COMPOSTO por host, no laudo.

Um scanner trata cada achado isolado. Dois arquivos sensíveis no MESMO host são
qualitativamente piores que um em cada: `/.git/HEAD` (código-fonte) + `/.env`
(segredos) juntos é a receita de takeover. Esta função ANOTA essa combinação.

Invariante desta camada: **NUNCA altera severidade nem cria `Finding`.** Elevar a
severidade automaticamente seria laudo especulativo — a severidade é a do caminho
curado, decidida por humano. Aqui só se AGRUPA o que o motor já achou; a anotação
é um item separado, sem campo de severidade. Função pura sobre `Finding`, sem I/O.
"""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

from webqa.dominio import Finding

# Combinações perigosas: conjunto de categorias que, JUNTAS no mesmo host, viram
# anotação. Curado e conservador — só o que é inequivocamente composto. Ampliar
# aqui é decisão humana, como a lista de caminhos.
COMBOS: tuple[tuple[frozenset[str], str, str], ...] = (
    (frozenset({"vcs", "configuracao"}), "codigo-fonte-e-segredos",
     "Código-fonte (VCS) e configuração/segredos expostos no mesmo host — "
     "risco de takeover (o invasor lê o código E as credenciais para operá-lo)."),
)


def _host(recurso: str) -> str:
    return urlsplit(recurso).hostname or ""


def _categoria(tipo: str) -> str:
    # tipo nasce "exposicao:<categoria>"; fora desse formato, usa o tipo inteiro.
    return tipo.split(":", 1)[1] if ":" in tipo else tipo


def correlacionar_findings(findings: Iterable[Finding]) -> list[dict]:
    """Anotações de risco composto por host. NÃO altera severidade nem cria
    Finding — só agrupa combinações já achadas. Determinística (ordenada)."""
    por_host: dict[str, list[Finding]] = {}
    for f in findings:
        por_host.setdefault(_host(f.recurso), []).append(f)

    anotacoes: list[dict] = []
    for host, fs in sorted(por_host.items()):
        categorias = {_categoria(f.tipo) for f in fs}
        for combo, nome, nota in COMBOS:
            if combo <= categorias:
                componentes = sorted(f.recurso for f in fs if _categoria(f.tipo) in combo)
                anotacoes.append({
                    "host": host,
                    "tipo": f"risco-composto:{nome}",
                    "componentes": componentes,
                    "nota": nota,
                })
    return anotacoes
