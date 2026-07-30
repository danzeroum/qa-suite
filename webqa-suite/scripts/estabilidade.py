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
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PADRAO = ROOT / "report" / "summary.json"
LEDGER_PADRAO = ROOT / "docs" / "lgpd-estabilidade.json"
META_PADRAO = 10
# schema 2: entradas ganham "origem" e "dia_utc"; sequência recalculada do
#           histórico, contando só o ambiente oficial e um dia por vez.
# schema 3: EMENDA de arquitetura (2026-07-30) — o ambiente oficial deixa de ser
#           o runner do GitHub e passa a ser o container Docker da VPS, com
#           imagem fixada por digest. A origem não é mais DETECTADA
#           (GITHUB_ACTIONS), é DECLARADA por WEBQA_ORIGEM, injetada somente no
#           container oficial. Entradas "ci" anteriores viram histórico.
SCHEMA = 3

# Só este ambiente move a métrica. Um runner hospedado troca a imagem base sob
# os pés; um container fixado por digest não — logo é MAIS controlado, e é dele
# que a sequência fala.
ORIGEM_OFICIAL = "vps"
ORIGENS_VALIDAS = ("vps", "ci", "local")

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
        return {"schema": SCHEMA, "execucoes": []}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados.setdefault("execucoes", [])
    return dados


def origem_da_execucao() -> str:
    """Origem DECLARADA em WEBQA_ORIGEM: vps | ci | local.

    Valor ausente ou desconhecido degrada para "local" — fail-safe deliberado:
    um erro de digitação no compose jamais pode inflar a métrica de confiança.
    No pior caso a execução deixa de contar; nunca conta errado.

    Não é prova criptográfica de proveniência — é declaração do ambiente, e quem
    tem push no repositório pode escrever o que quiser no ledger. A barreira
    existe contra descuido, não contra falsificação deliberada.
    """
    declarada = (os.environ.get("WEBQA_ORIGEM") or "local").strip().lower()
    return declarada if declarada in ORIGENS_VALIDAS else "local"


def _dia_utc_de(entrada: dict) -> str:
    """Dia UTC da entrada; cai para o prefixo de generated_at se o campo faltar.

    O fallback cobre a entrada anterior à migração, gravada por um runner do
    Actions (TZ=UTC) — logo o prefixo É o dia UTC.
    """
    return str(entrada.get("dia_utc") or str(entrada.get("generated_at", ""))[:10])


def sequencia_oficial(execucoes: list[dict],
                      origem_oficial: str = ORIGEM_OFICIAL) -> tuple[int, int]:
    """(sequência sem flake, dias distintos) contando SÓ o ambiente oficial.

    Recalculada do histórico inteiro a cada rodada, em vez de incrementada a
    partir da última entrada: o valor gravado passa a ser derivável e auditável,
    e uma entrada inserida fora de ordem não contamina o resto.

    Três regras:

    * `origem != origem_oficial` não conta — inclui as entradas `ci` anteriores
      à emenda, que permanecem no ledger como HISTÓRICO, e as `local`;
    * no máximo UMA por dia UTC, e vale a PRIMEIRA do dia: uma segunda execução
      no mesmo dia não infla a sequência;
    * a sequência é por alvo — se o `alvo_sha256` muda entre dias contados,
      recomeça.
    """
    primeira_do_dia: dict[str, dict] = {}
    for entrada in execucoes:
        if entrada.get("origem") != origem_oficial:
            continue
        primeira_do_dia.setdefault(_dia_utc_de(entrada), entrada)

    streak = 0
    alvo_anterior: str | None = None
    for dia in sorted(primeira_do_dia):
        entrada = primeira_do_dia[dia]
        if alvo_anterior is not None and entrada.get("alvo_sha256") != alvo_anterior:
            streak = 0
        limpa = int(entrada.get("infra_flakes", 0)) == 0 and int(entrada.get("browser_total", 0)) > 0
        streak = streak + 1 if limpa else 0
        alvo_anterior = entrada.get("alvo_sha256")
    return streak, len(primeira_do_dia)


@dataclass(frozen=True)
class Registro:
    """O que aconteceu ao tentar registrar a execução."""

    streak: int
    entrada: dict | None
    dias: int = 0
    origem: str = "local"
    duplicada: bool = False
    ignorada: bool = False
    alvo_mudou: bool = False


def registrar(ledger: dict, classificacao: Classificacao, alvo_sha256: str,
              origem: str | None = None, dia_utc: str | None = None) -> Registro:
    """Aplica a execução ao ledger (em memória) e devolve o que mudou."""
    execucoes = ledger["execucoes"]
    origem = origem or origem_da_execucao()
    streak_atual, dias_atuais = sequencia_oficial(execucoes)

    # generated_at é a chave: rodar o script duas vezes no mesmo summary não
    # infla a sequência nem cria entrada duplicada.
    for entrada in execucoes:
        if entrada.get("generated_at") == classificacao.generated_at:
            return Registro(streak=streak_atual, entrada=entrada, dias=dias_atuais,
                            origem=str(entrada.get("origem", "local")), duplicada=True)

    # Execução sem nenhum teste de navegador não diz nada sobre a estabilidade
    # do network_log: não conta e não zera.
    if not classificacao.tem_browser:
        return Registro(streak=streak_atual, entrada=None, dias=dias_atuais,
                        origem=origem, ignorada=True)

    anterior_oficial = next(
        (e for e in reversed(execucoes) if e.get("origem") == ORIGEM_OFICIAL), None
    )
    alvo_mudou = bool(anterior_oficial
                      and anterior_oficial.get("alvo_sha256") != alvo_sha256)

    entrada = {
        "generated_at": classificacao.generated_at,
        # Dia vem do generated_at do summary, não do relógio de agora: o script
        # pode rodar minutos (ou um retry) depois da suíte, e o dia que importa é
        # o da EXECUÇÃO. Nos runners do Actions TZ=UTC — e são justamente as
        # entradas de CI que a deduplicação por dia considera.
        "dia_utc": dia_utc or classificacao.generated_at[:10],
        "origem": origem,
        "alvo_sha256": alvo_sha256,
        "browser_total": classificacao.browser_total,
        "infra_flakes": len(classificacao.flakes),
    }
    execucoes.append(entrada)
    # `streak` gravado = sequência de CI DEPOIS desta entrada. Numa entrada
    # local ele repete o valor anterior, deixando explícito que nada mudou.
    streak, dias = sequencia_oficial(execucoes)
    entrada["streak"] = streak
    ledger["schema"] = SCHEMA
    return Registro(streak=streak, entrada=entrada, dias=dias, origem=origem,
                    alvo_mudou=alvo_mudou and origem == ORIGEM_OFICIAL)


def _resolver_alvo(explicito: str | None, usar_fixture: bool = False) -> str:
    if usar_fixture:
        # A identidade do fixture vem do que ele SERVE, não da URL: a porta é
        # efêmera e mudaria a cada noite, zerando a sequência para sempre.
        sys.path.insert(0, str(ROOT))
        from fixture_target.servir import identidade

        return identidade()
    if explicito:
        return explicito
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
    parser.add_argument("--alvo-fixture", action="store_true",
                        help="usa a identidade do alvo fixture (estável entre execuções, "
                             "ao contrário da porta efêmera)")
    parser.add_argument("--meta", type=int, default=META_PADRAO)
    parser.add_argument("--dry-run", action="store_true",
                        help="classifica e imprime sem gravar (uso em CI, que não commita)")
    args = parser.parse_args(argv)

    if not args.summary.exists():
        print(f"summary não encontrado: {args.summary} — rode a suíte antes.", file=sys.stderr)
        return 2

    classificacao = classificar(json.loads(args.summary.read_text(encoding="utf-8")))
    alvo = _resolver_alvo(args.alvo, usar_fixture=args.alvo_fixture)
    if not alvo:
        print("alvo indeterminado: defina WEBQA_TARGET_URL, use --alvo ou --alvo-fixture.",
              file=sys.stderr)
        return 2

    ledger = carregar_ledger(args.ledger)
    registro = registrar(ledger, classificacao, sha256_do_alvo(alvo))

    def _placar() -> str:
        plural = "dia" if registro.dias == 1 else "dias"
        distintos = "distinto" if registro.dias == 1 else "distintos"
        placar = (f"streak {registro.streak}/{args.meta} "
                  f"({ORIGEM_OFICIAL}, {registro.dias} {plural} {distintos})")
        # Entradas de antes da emenda continuam no ledger; dizer isso evita que
        # alguém leia "0/10" como perda de histórico.
        historicas = sum(1 for e in ledger["execucoes"] if e.get("origem") == "ci")
        if historicas:
            placar += f" · histórico: {historicas} execução(ões) 'ci' anterior(es), fora da conta"
        return placar

    if registro.ignorada:
        print("Execução sem testes de navegador — ignorada (não conta nem zera). "
              f"{_placar()}")
        return 0
    if registro.duplicada:
        print(f"Execução {classificacao.generated_at} já registrada — nada a fazer. "
              f"{_placar()}")
        return 0

    if registro.alvo_mudou:
        print(f"Alvo mudou desde a última execução '{ORIGEM_OFICIAL}': sequência "
              "reiniciada (métrica é por alvo).")
    if classificacao.limpa:
        print(f"Execução limpa: {classificacao.browser_total} testes de navegador, 0 flakes.")
    else:
        print(f"Flake de INFRA em {len(classificacao.flakes)} de {classificacao.browser_total} "
              "testes de navegador.")
        for teste in classificacao.flakes[:5]:
            print(f"  - {teste}")

    dia = registro.entrada["dia_utc"] if registro.entrada else "?"
    if registro.origem == ORIGEM_OFICIAL:
        print(f"Origem: {ORIGEM_OFICIAL} — conta no máximo uma vez por dia UTC (dia {dia}).")
    else:
        # Registrada para auditoria, mas fora da métrica: execução em ambiente
        # não oficial não é evidência de estabilidade do ambiente oficial.
        print(f"Origem: {registro.origem} — entrada informativa, NÃO avança nem zera "
              f"a sequência (só '{ORIGEM_OFICIAL}' conta; declare WEBQA_ORIGEM no "
              "container oficial).")

    if not args.dry_run:
        args.ledger.parent.mkdir(parents=True, exist_ok=True)
        args.ledger.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    print(_placar() + (" (dry-run: ledger não gravado)" if args.dry_run else ""))
    if registro.streak >= args.meta:
        print("FASE 2 DESTRAVADA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
