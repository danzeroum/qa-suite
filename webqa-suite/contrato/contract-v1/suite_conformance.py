#!/usr/bin/env python3
"""Kit de conformidade — rodável dos DOIS lados do contrato.

Um contrato que só o consumidor consegue verificar não é contrato: é a régua descobrindo que
quebrou a promessa quando quebrou o CI de outra pessoa. Por isso o mesmo código responde a duas
perguntas, e a direção é escolhida por flag:

  --as-suite      "eu, a régua, emito envelope conforme a contract-vN?"
  --as-consumer   "eu, o consumidor, tenho pin e ficha que honram o contrato?"

O LADO DA SUÍTE É O QUE JUSTIFICA O KIT EXISTIR COMO ARQUIVO SEPARADO. `ci/audit_suites.py`
fiscaliza ESTE repositório e depende do registro, dos ADRs e do harness_lib. Uma régua não tem
nada disso — ela tem um laudo de exemplo e o contrato. Este modo roda com o contrato e um JSON,
e é copiável para dentro da suíte sem trazer meio molde junto: a mesma fronteira de dados que o
motor de mutação respeita.

Uso:
  python ci/suite_conformance.py --as-suite LAUDO.json [--contract v1]
  python ci/suite_conformance.py --as-consumer NOME
Saída: 0 conforme · 1 não conforme · 2 não foi possível verificar.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

CLAUSULAS = ("pin-fonte-unica", "release-com-manifesto", "envelope-com-3-estados",
             "fingerprint", "autoprova-de-mordida")

FINGERPRINT = ("name", "version", "commit", "catalog_hash", "schema_version")

# Mapa entre o nome canônico do fingerprint e onde ele mora no envelope. `catalog_hash` é o nome
# GERAL do que a procedência chama de `sensitive_paths_hash` — a lista curada de uma régua de QA é
# um catálogo entre outros, e o contrato nomeia a categoria, não o caso.
ONDE_NO_ENVELOPE = {
    "name": ("standard", "name"),
    "version": ("standard", "version"),
    "commit": ("standard", "commit"),
    "catalog_hash": ("standard", "sensitive_paths_hash"),
    "schema_version": ("schema_version",),
}


def raiz() -> Path:
    return Path(os.environ.get("HARNESS_REPO_ROOT") or Path(__file__).resolve().parent.parent)


def _cavar(doc: dict, caminho: tuple[str, ...]):
    no = doc
    for parte in caminho:
        if not isinstance(no, dict) or parte not in no:
            return None
        no = no[parte]
    return no


def como_suite(laudo_path: str, contrato: str, quiet: bool) -> int:
    """A régua prova que emite envelope conforme. Só precisa do laudo e do contrato."""
    alvo = Path(laudo_path)
    if not alvo.is_file():
        print(f"✗ não consegui verificar: {laudo_path} não existe.", file=sys.stderr)
        return 2
    try:
        laudo = json.loads(alvo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"✗ não consegui verificar: {laudo_path} não é JSON ({exc}).", file=sys.stderr)
        return 2

    falhas: list[str] = []

    # Cláusula 3 — os três estados, e a coerência entre result e verdict.
    veredito = laudo.get("verdict")
    if veredito is None:
        falhas.append(
            "cláusula 3: o laudo não declara `verdict`. Sem ele, o consumidor precisa INFERIR o "
            "que o laudo significa — e inferência não é laudo. É o estado em que 'não consegui "
            "medir' sai com a mesma cor de 'medi e está bom'.")
    elif veredito not in ("conforme", "nao_conforme", "inconclusivo"):
        falhas.append(f"cláusula 3: verdict '{veredito}' não é um dos três estados.")
    else:
        resultado = laudo.get("result")
        if resultado in ("suite_not_installed", "error") and veredito != "inconclusivo":
            falhas.append(
                f"cláusula 3: result={resultado} com verdict={veredito}. Não ter medido só pode "
                f"produzir 'inconclusivo'.")
        if veredito == "conforme" and resultado != "ok":
            falhas.append(
                f"cláusula 3: verdict=conforme com result={resultado}. 'Conforme' é o único "
                f"veredito que exige ausência de achado.")

    # Cláusula 4 — o fingerprint completo.
    for campo in FINGERPRINT:
        if _cavar(laudo, ONDE_NO_ENVELOPE[campo]) in (None, ""):
            falhas.append(
                f"cláusula 4: fingerprint sem '{campo}'. Faltando um campo, dois laudos parecem "
                f"comparáveis sem serem, e a diferença entre eles deixa de significar o que se "
                f"pensa que significa.")

    if falhas:
        print(f"✗ a régua NÃO é conforme à contract-{contrato} ({len(falhas)}):", file=sys.stderr)
        for f in falhas:
            print(f"  - {f}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"✓ o laudo satisfaz a contract-{contrato}: três estados coerentes e fingerprint "
              f"completo.")
    return 0


def como_consumidor(nome: str, quiet: bool) -> int:
    """O consumidor prova que o pin e a ficha honram o contrato.

    Reusa `ci/audit_suites.py` em vez de reimplementar as cláusulas: duas respostas para a mesma
    pergunta é a deriva que este repositório recusa em toda parte. O que este modo acrescenta é
    o RECORTE — falar de uma régua só, e sair com o código que o CI daquela régua espera.
    """
    sys.path.insert(0, str(raiz() / "ci"))
    import audit_suites
    import harness_lib as hl

    rel = f"harness/suites/{nome}.yaml"
    if not hl.rel_exists(rel):
        print(f"✗ não consegui verificar: não existe ficha em {rel}.", file=sys.stderr)
        return 2

    findings, errors = hl.Findings(), hl.Errors()
    try:
        audit_suites._auditar(findings, errors, autoprova=False)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ não consegui verificar: {exc}", file=sys.stderr)
        return 2
    if errors:
        for e in errors.items:
            print(f"✗ não consegui verificar: {e}", file=sys.stderr)
        return 2

    alvo = nome.upper()
    meus = [i for i in findings.blocking() if f"-{alvo}-" in i["id"] or i["id"].endswith(alvo)]
    if meus:
        print(f"✗ o consumo de {nome} NÃO honra o contrato ({len(meus)}):", file=sys.stderr)
        for i in meus:
            print(f"  - [{i['severity']}] {i['id']}: {i['summary']}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"✓ o consumo de {nome} honra o contrato: pin, release, envelope e fingerprint.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kit de conformidade do Contrato de Régua.")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--as-suite", metavar="LAUDO",
                       help="caminho de um laudo; prova que a RÉGUA emite envelope conforme")
    grupo.add_argument("--as-consumer", metavar="NOME",
                       help="nome de uma ficha; prova que o CONSUMIDOR honra o contrato")
    parser.add_argument("--contract", default="v1")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if args.as_suite:
        return como_suite(args.as_suite, args.contract, args.quiet)
    return como_consumidor(args.as_consumer, args.quiet)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
