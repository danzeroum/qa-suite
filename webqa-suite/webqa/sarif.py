"""Exportação SARIF 2.1.0 dos achados da Fase C — para a aba Security do GitHub.

Função PURA sobre `Finding`: sem I/O, sem rede. Só usa campos que o `Finding`
JÁ mascarou no construtor (`recurso`, `evidencia`, `remediacao`, `procedencia`),
então nada de segredo em claro chega ao SARIF — a mesma garantia estrutural do
laudo. `nivel` mapeia a severidade curada para o vocabulário do SARIF; um achado
`error` (severidade alta) é o que faz o CI reprovar e aparecer na aba Security.

Somente stdlib.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

from webqa.dominio import Finding

FERRAMENTA = "WebQA-FaseC"

# Publicos porque a dimensao `gui` emite SARIF proprio (webqa/conformidade.py,
# OS-53) e precisa do MESMO schema e da MESMA versao. Duas constantes iguais em
# dois modulos divergiriam no primeiro upgrade de schema, e a divergencia
# apareceria como um exportador aceito e o outro recusado pela mesma
# ferramenta — a licao do _contextos_de_gui aplicada a serializacao.
SCHEMA_SARIF = "https://json.schemastore.org/sarif-2.1.0.json"
VERSAO_SARIF = "2.1.0"

_SCHEMA = SCHEMA_SARIF

# Severidade curada → nível SARIF. Alta = error (reprova o CI / aba Security).
_NIVEL = {"alta": "error", "media": "warning", "baixa": "note"}


def _resultado(f: Finding) -> dict:
    return {
        "ruleId": f.tipo,
        "level": _NIVEL.get(f.severidade, "warning"),
        "message": {"text": f.evidencia},
        "locations": [{
            "physicalLocation": {"artifactLocation": {"uri": f.recurso}},
        }],
        # Campos já mascarados; procedencia/remediacao ajudam a triagem no GitHub.
        "properties": {
            "severidade": f.severidade,
            "fase": f.fase,
            "procedencia": f.procedencia,
            "remediacao": f.remediacao,
        },
    }


def para_sarif(findings: Iterable[Finding]) -> dict:
    """Documento SARIF 2.1.0 com um `result` por achado. Puro e determinístico."""
    findings = list(findings)
    regras = {
        f.tipo: {"id": f.tipo,
                 "shortDescription": {"text": f.tipo},
                 "defaultConfiguration": {"level": _NIVEL.get(f.severidade, "warning")}}
        for f in findings
    }
    return {
        "version": VERSAO_SARIF,
        "$schema": _SCHEMA,
        "runs": [{
            "tool": {"driver": {"name": FERRAMENTA, "rules": list(regras.values())}},
            "results": [_resultado(f) for f in findings],
        }],
    }


def serializar_sarif(findings: Iterable[Finding]) -> str:
    """SARIF como texto JSON estável (chaves ordenadas), pronto para gravar."""
    return json.dumps(para_sarif(findings), ensure_ascii=False, sort_keys=True, indent=2)
