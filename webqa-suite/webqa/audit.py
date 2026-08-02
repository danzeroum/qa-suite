"""Auditoria append-only da Fase C — uma linha por requisição ativa.

Registra o que foi pedido, quando, contra qual alvo e sob qual autorização. Três
proteções, todas antes de a linha existir no arquivo:

* **mascaramento por valor** (`sanitize.sanitize_text`) — segredo registrado não
  vaza para o log, mesmo que apareça numa URL ou num header de erro (R-C8);
* **supressão de query-string** — um caminho sensível não tem query legítima;
  qualquer `?token=` em `/.git/HEAD` é suspeito e não é gravado;
* **escape de caractere de controle** — um servidor que devolva `\n[CRITICAL]…`
  não pode injetar linha falsa no log (R-C15).

`AuditLog` é injetável: `sondagem` recebe uma instância; o teste injeta uma em
memória (sem `caminho`) e inspeciona `.linhas`. SRP como `gates.py` — a auditoria
não conhece HTTP nem o ciclo de vida do pytest. Sem rede.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from webqa.sanitize import sanitize_text

_CONTROLE = {ord("\r"): "\\r", ord("\n"): "\\n", ord("\t"): "\\t"}
_MAX_CAMPO = 500


def _limpar(valor) -> str:
    """Mascara segredo, escapa controle e trunca — nesta ordem."""
    return sanitize_text(str(valor)).translate(_CONTROLE)[:_MAX_CAMPO]


def _url_sem_query(url: str) -> str:
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


class AuditLog:
    """Log de auditoria de um run. Append-only; nunca reescreve linha anterior."""

    def __init__(self, run_id: str, escopo_hash: str, caminho: str | Path | None = None) -> None:
        self.run_id = run_id
        self.escopo_hash = escopo_hash
        self._caminho = Path(caminho) if caminho else None
        self._linhas: list[dict] = []
        if self._caminho is not None:
            self._caminho.parent.mkdir(parents=True, exist_ok=True)

    def registrar(self, *, url: str, metodo: str, alvo: str, autorizacao_id: str,
                  status: int | None = None, evento: str | None = None) -> dict:
        linha = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": _limpar(self.run_id),
            "escopo_hash": self.escopo_hash,
            "alvo": _limpar(alvo),
            "autorizacao_id": _limpar(autorizacao_id),
            "metodo": _limpar(metodo),
            "url": _limpar(_url_sem_query(url)),
            "status": status,
            "evento": _limpar(evento) if evento else None,
        }
        self._linhas.append(linha)
        if self._caminho is not None:
            with self._caminho.open("a", encoding="utf-8") as f:
                f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        return linha

    @property
    def linhas(self) -> tuple[dict, ...]:
        return tuple(self._linhas)
