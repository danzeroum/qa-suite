#!/usr/bin/env python3
"""Ledger de estabilidade da dimensão browser — critério de saída da Fase 1.

A Fase 2 (canário de consentimento, CMPs) foi condicionada pela arquitetura à
estabilidade da infraestrutura de `network_log` em produção. "Estável" precisa
ser um número verificável, não uma impressão: este script conta execuções
CONSECUTIVAS sem falha de infraestrutura e registra cada uma no ledger.

A distinção que dá sentido à métrica:

* **flake de infra** — Timeout, TargetClosed, `net::`, Chromium ausente.
  É defeito do AMBIENTE DE TESTE. Zera a sequência.
* **FAIL determinístico** — tracker antes do consentimento, cookie de 730 dias.
  É veredito sobre o ALVO, e a suíte funcionou exatamente como deveria.
  NÃO zera a sequência; um alvo não conforme não torna a suíte instável.

Privacidade: a URL do alvo NUNCA entra no ledger, só o sha256. O digest serve
para correlacionar execuções do mesmo alvo — não é segredo (o espaço de URLs é
pequeno e enumerável), é chave de agrupamento.

Somente stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PADRAO = ROOT / "report" / "summary.json"
LEDGER_PADRAO = ROOT / "docs" / "lgpd-estabilidade.json"
META_PADRAO = 10

# Assinaturas de falha do ambiente de teste — nunca de conformidade do alvo.
#
# SEM re.IGNORECASE e com limite de palavra, de propósito: o pytest inclui no
# longrepr o cabeçalho de argumentos das fixtures, onde aparece
# `Settings(..., timeout_s=15.0, ...)`. Casar "timeout" sem caixa transformava
# TODA falha determinística num falso flake — a sequência nunca sairia de zero.
INFRA = re.compile(
    r"\bTimeout(?:Error)?\b"          # Playwright: "Timeout 60000ms exceeded" / TimeoutError
    r"|\bTargetClosed"                # página/contexto fechado no meio do teste
    r"|net::"                         # erros de rede do Chromium (net::ERR_*)
    r"|Chromium indispon"             # skip da fixture browser
    r"|Playwright n[ãa]o instalado"   # skip da fixture browser
)


@dataclass(frozen=True)
class Classificacao:
    """Veredito sobre UMA execução da suíte."""

    generated_at: str
    browser_total: int
    flakes: tuple[str, ...]

    @property
    def tem_browser(self) -> bool:
        return self.browser_total > 0

    @property
    def limpa(self) -> bool:
        return self.tem_browser and not self.flakes


def classificar(summary: dict) -> Classificacao:
    """Separa flake de infra de veredito sobre o alvo."""
    browser = [r for r in summary.get("results", []) if r.get("browser")]
    flakes = tuple(
        r.get("test", "?")
        for r in browser
        if r.get("outcome") != "passed" and INFRA.search(r.get("detail") or "")
    )
    return Classificacao(
        generated_at=str(summary.get("generated_at", "")),
        browser_total=len(browser),
        flakes=flakes,
    )


def sha256_do_alvo(target_url: str) -> str:
    return hashlib.sha256(target_url.encode("utf-8")).hexdigest()


def carregar_ledger(caminho: Path) -> dict:
    if not caminho.exists():
        return {"schema": 1, "execucoes": []}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados.setdefault("execucoes", [])
    return dados


@dataclass(frozen=True)
class Registro:
    """O que aconteceu ao tentar registrar a execução."""

    streak: int
    entrada: dict | None
    duplicada: bool = False
    ignorada: bool = False
    alvo_mudou: bool = False


def registrar(ledger: dict, classificacao: Classificacao, alvo_sha256: str) -> Registro:
    """Aplica a execução ao ledger (em memória) e devolve o que mudou."""
    execucoes = ledger["execucoes"]

    # generated_at é a chave: rodar o script duas vezes no mesmo summary não
    # infla a sequência nem cria entrada duplicada.
    for entrada in execucoes:
        if entrada.get("generated_at") == classificacao.generated_at:
            return Registro(streak=int(entrada.get("streak", 0)), entrada=entrada, duplicada=True)

    # Execução sem nenhum teste de navegador não diz nada sobre a estabilidade
    # do network_log: não conta e não zera.
    if not classificacao.tem_browser:
        anterior = execucoes[-1] if execucoes else None
        return Registro(streak=int(anterior.get("streak", 0)) if anterior else 0,
                        entrada=None, ignorada=True)

    anterior = execucoes[-1] if execucoes else None
    alvo_mudou = bool(anterior and anterior.get("alvo_sha256") != alvo_sha256)
    # Sequência é por alvo: 9 execuções limpas contra um alvo e 1 contra outro
    # não são 10 execuções limpas contra nada.
    base = 0 if (anterior is None or alvo_mudou) else int(anterior.get("streak", 0))
    streak = base + 1 if classificacao.limpa else 0

    entrada = {
        "generated_at": classificacao.generated_at,
        "alvo_sha256": alvo_sha256,
        "browser_total": classificacao.browser_total,
        "infra_flakes": len(classificacao.flakes),
        "streak": streak,
    }
    execucoes.append(entrada)
    return Registro(streak=streak, entrada=entrada, alvo_mudou=alvo_mudou)


def _resolver_alvo(explicito: str | None) -> str:
    if explicito:
        return explicito
    import os

    if os.environ.get("WEBQA_TARGET_URL"):
        return os.environ["WEBQA_TARGET_URL"]
    try:  # reusa a resolução oficial (config.yaml + env) em vez de duplicá-la
        sys.path.insert(0, str(ROOT))
        from webqa.config import load_settings

        return load_settings().target_url
    except Exception:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("summary", nargs="?", type=Path, default=SUMMARY_PADRAO)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PADRAO)
    parser.add_argument("--alvo", default=None, help="URL do alvo (só o sha256 é gravado)")
    parser.add_argument("--meta", type=int, default=META_PADRAO)
    parser.add_argument("--dry-run", action="store_true",
                        help="classifica e imprime sem gravar (uso em CI, que não commita)")
    args = parser.parse_args(argv)

    if not args.summary.exists():
        print(f"summary não encontrado: {args.summary} — rode a suíte antes.", file=sys.stderr)
        return 2

    classificacao = classificar(json.loads(args.summary.read_text(encoding="utf-8")))
    alvo = _resolver_alvo(args.alvo)
    if not alvo:
        print("alvo indeterminado: defina WEBQA_TARGET_URL ou use --alvo.", file=sys.stderr)
        return 2

    ledger = carregar_ledger(args.ledger)
    registro = registrar(ledger, classificacao, sha256_do_alvo(alvo))

    if registro.ignorada:
        print("Execução sem testes de navegador — ignorada (não conta nem zera). "
              f"Sequência segue em {registro.streak}.")
        return 0
    if registro.duplicada:
        print(f"Execução {classificacao.generated_at} já registrada — nada a fazer. "
              f"Sequência: {registro.streak}.")
        return 0

    if registro.alvo_mudou:
        print("Alvo mudou desde a última execução: sequência reiniciada (métrica é por alvo).")
    if classificacao.limpa:
        print(f"Execução limpa: {classificacao.browser_total} testes de navegador, 0 flakes.")
    else:
        print(f"Flake de INFRA em {len(classificacao.flakes)} de {classificacao.browser_total} "
              f"testes de navegador — sequência zerada.")
        for teste in classificacao.flakes[:5]:
            print(f"  - {teste}")

    if not args.dry_run:
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    print(f"Sequência sem flake: {registro.streak}/{args.meta}"
          + (" (dry-run: ledger não gravado)" if args.dry_run else ""))
    if registro.streak >= args.meta:
        print("FASE 2 DESTRAVADA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
