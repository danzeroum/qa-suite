"""Monta report/medicoes.json (D5k) — a MEDIÇÃO que o cockpit exibe.

Separação de trabalho: medir é aqui (lê coverage, roda ruff C901, lê o score de
mutação), exibir é do cockpit (scripts/cockpit.py só LÊ este arquivo). Cada bloco
é opcional: fonte ausente → bloco ausente → o motor mostra "não instrumentada",
nunca 0%/verde. Nada aqui toca a rede.

Fontes:
* cobertura → `report/coverage.json` (de `coverage json`, após um run --cov);
* complexidade → `ruff --select C901` sobre webqa/ (sempre disponível, estático);
* mutação → `report/mutacao.json` (de scripts/mutar.py; roda no noturno).

Uso:  python scripts/medicoes.py            # escreve report/medicoes.json
      python scripts/medicoes.py --json     # imprime no stdout

Somente stdlib.
"""
from __future__ import annotations

import argparse
import json
import re

# argv fixo, sem shell, e ruff invocado por `sys.executable -m ruff` (caminho
# completo do interpretador, sem depender do PATH). Ver a mesma nota em campanha.py.
import subprocess  # nosec B404
import sys
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
TETO_COMPLEXIDADE = 8
TOP_CAUDA = 12
_CC_RE = re.compile(r"\((\d+) > \d+\)")        # "(9 > 0)"
_FUNC_RE = re.compile(r"`([^`]+)`")            # "`nome`"
_VIES = ("o gate de cobertura roda só a população verification; caminhos "
         "exercitados por checks/ contra o alvo aparecem descobertos")


def cobertura_de(cov: dict) -> dict:
    """coverage.py json → {total, por_arquivo, vies}. Puro, testável."""
    total = round(float(cov.get("totals", {}).get("percent_covered", 0.0)), 1)
    por_arquivo = {
        arq: round(float(d.get("summary", {}).get("percent_covered", 0.0)), 1)
        for arq, d in cov.get("files", {}).items()
    }
    return {"total": total, "por_arquivo": por_arquivo, "vies": _VIES}


def complexidade_de(itens: list, teto: int = TETO_COMPLEXIDADE,
                    topn: int = TOP_CAUDA, raiz: Path | None = None) -> dict:
    """Achados C901 do ruff (com max-complexity=0, todos as funções) → a cauda das
    mais complexas + a decisão do limiar. Puro, testável."""
    cauda = []
    for it in itens:
        if it.get("code") != "C901":
            continue
        cc_m = _CC_RE.search(it.get("message", ""))
        func_m = _FUNC_RE.search(it.get("message", ""))
        if not cc_m:
            continue
        arquivo = it.get("filename", "")
        if raiz is not None:
            arquivo = _relativo(arquivo, raiz)
        cauda.append({"func": func_m.group(1) if func_m else "?",
                      "arquivo": arquivo, "cc": int(cc_m.group(1))})
    cauda.sort(key=lambda c: (-c["cc"], c["arquivo"], c["func"]))
    return {"teto": teto, "cauda": cauda[:topn]}


def _relativo(caminho: str, raiz: Path) -> str:
    try:
        return Path(caminho).resolve().relative_to(raiz.resolve()).as_posix()
    except ValueError:
        return caminho


def _ler_json(caminho: Path) -> dict | None:
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _ruff_c901(raiz: Path) -> list:
    """Roda `ruff --select C901` com teto 0 (reporta TODAS as funções e o CC de
    cada) sobre webqa/. Falha do ruff → lista vazia (complexidade fica ausente)."""
    try:
        proc = subprocess.run(  # nosec B603
            [sys.executable, "-m", "ruff", "check", "webqa", "--select", "C901",
             "--config", "lint.mccabe.max-complexity=0", "--output-format", "json"],
            cwd=raiz, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []


def montar_medicoes(raiz: Path) -> dict:
    """Reúne os blocos disponíveis. Bloco cuja fonte falta simplesmente não entra —
    o cockpit o mostra como 'não instrumentada'."""
    medicoes: dict = {}
    cov = _ler_json(raiz / "report" / "coverage.json")
    if cov is not None:
        medicoes["cobertura_codigo"] = cobertura_de(cov)
    itens = _ruff_c901(raiz)
    if itens:
        medicoes["complexidade"] = complexidade_de(itens, raiz=raiz)
    mut = _ler_json(raiz / "report" / "mutacao.json")
    if mut is not None:
        medicoes["mutacao"] = mut
    return medicoes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO)
    parser.add_argument("--json", action="store_true", help="imprime no stdout")
    args = parser.parse_args(argv)
    medicoes = montar_medicoes(args.raiz)
    texto = json.dumps(medicoes, ensure_ascii=False, indent=1)
    if args.json:
        print(texto)
        return 0
    destino = args.raiz / "report" / "medicoes.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    presentes = ", ".join(medicoes) or "nenhum bloco (fontes ausentes)"
    print(f"medicoes: {destino} — {presentes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
