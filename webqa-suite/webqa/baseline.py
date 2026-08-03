"""Ciclo de vida do achado da Fase C contra um `baseline.yaml` versionado.

O baseline separa o RUÍDO conhecido do SINAL novo. Sem ele, todo run repete os
mesmos achados persistentes e o operador para de olhar — e o achado NOVO se perde
no meio. Com ele:

* **novo** — chave inédita → REPROVA o pipeline (é o que exige ação);
* **reaberto** — estava no baseline marcado como corrigido/desaparecido e voltou
  → REPROVA (regressão é tão grave quanto achado novo);
* **persistente** — já conhecido e aceito no baseline → silenciado (não reprova);
* **desaparecido** — estava no baseline (persistente) e sumiu do run → NÃO é
  removido automaticamente: vira "possível correção" para REVISÃO MANUAL. Remoção
  automática apagaria a memória de uma exposição que pode ter só ficado
  intermitente (o alvo caiu, o WAF bloqueou) — o oposto de auditar.

Função pura sobre `Finding` + dict do baseline; sem I/O além de `carregar`
(PyYAML, já dependência). A identidade do achado é `tipo|recurso` — o mesmo par
que o laudo mostra.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from webqa.dominio import Finding

# Estados que uma entrada do baseline pode carregar.
PERSISTENTE = "persistente"
CORRIGIDO = "corrigido"       # marcado como resolvido; se voltar, é REABERTURA


def chave(finding: Finding) -> str:
    """Identidade estável do achado: `tipo|recurso` (o par que o laudo exibe)."""
    return f"{finding.tipo}|{finding.recurso}"


@dataclass(frozen=True)
class CicloDeVida:
    """Classificação de um run contra o baseline. `reprova` é o sinal do CI."""

    novos: tuple[Finding, ...] = ()
    reabertos: tuple[Finding, ...] = ()
    persistentes: tuple[Finding, ...] = ()
    desaparecidos: tuple[str, ...] = ()      # chaves — possível correção, revisão manual

    @property
    def reprova(self) -> bool:
        """Novo ou reaberto reprova o pipeline; persistente/desaparecido não."""
        return bool(self.novos or self.reabertos)


def carregar_baseline(path: str | Path) -> dict[str, str]:
    """Lê o baseline.yaml → {chave: estado}. Ausente = baseline vazio (tudo novo)."""
    p = Path(path)
    if not p.exists():
        return {}
    dados = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entradas = dados.get("achados") or []
    return {str(e["chave"]): str(e.get("estado", PERSISTENTE)) for e in entradas}


def classificar(findings: Iterable[Finding], baseline: dict[str, str]) -> CicloDeVida:
    """Classifica os achados do run contra o baseline. Puro e determinístico."""
    novos, reabertos, persistentes = [], [], []
    vistos: set[str] = set()
    for f in findings:
        k = chave(f)
        vistos.add(k)
        estado = baseline.get(k)
        if estado is None:
            novos.append(f)
        elif estado == CORRIGIDO:
            reabertos.append(f)          # voltou depois de marcado corrigido
        else:
            persistentes.append(f)       # PERSISTENTE (ou qualquer estado conhecido)
    # Persistentes do baseline que não apareceram agora: possível correção. NUNCA
    # removidos daqui — só sinalizados para revisão humana.
    desaparecidos = tuple(sorted(
        k for k, estado in baseline.items()
        if estado == PERSISTENTE and k not in vistos))
    return CicloDeVida(
        novos=tuple(novos), reabertos=tuple(reabertos),
        persistentes=tuple(persistentes), desaparecidos=desaparecidos)
