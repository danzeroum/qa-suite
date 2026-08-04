"""Comparador entre laudos de projetos (frente E, E5).

Aprovar é comparar — mas só é honesto comparar dois laudos medidos pela MESMA
régua. Este módulo é o guarda dessa honestidade: recusa alinhar laudos de réguas
diferentes, NOMEANDO o eixo que diverge (versão do padrão ou hash da lista
curada), e só então emite o lado a lado.

O que se compara sob régua comum (ARQUITETURA §8.3): a **cobertura de sondagem**
(quantos caminhos da régua cada projeto exercitou — `38/91` × `91/91` deixa de ser
incomparável) e os achados por severidade. Nunca um "delta de achados novos entre
projetos": recurso de projetos diferentes é host diferente, e somá-los ou casá-los
seria inventar equivalência.

Somente stdlib.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Os eixos que TÊM de casar para dois laudos serem comparáveis: a versão do padrão
# e o hash da lista curada (a régua). commit e caminhos_total não entram — commit
# varia por leitura e o total é derivado do hash.
EIXOS_DA_REGUA = ("versao", "caminhos_sensiveis_hash")


def _regua(laudo: dict) -> dict | None:
    """Os eixos de régua do laudo (do bloco `padrao`, E4), ou `None` se o laudo
    não traz carimbo — sem carimbo não há régua, e sem régua não há comparação."""
    padrao = laudo.get("padrao")
    if not isinstance(padrao, dict):
        return None
    if any(padrao.get(eixo) in (None, "") for eixo in EIXOS_DA_REGUA):
        return None
    return {eixo: padrao[eixo] for eixo in EIXOS_DA_REGUA}


def motivos_de_incompatibilidade(laudo_a: dict, laudo_b: dict) -> list[str]:
    """Lista NOMEADA do que impede a comparação — vazia se as réguas batem."""
    ra, rb = _regua(laudo_a), _regua(laudo_b)
    if ra is None or rb is None:
        faltantes = [rot for rot, r in (("A", ra), ("B", rb)) if r is None]
        return [f"laudo {rot} sem carimbo de régua (bloco `padrao` incompleto)"
                for rot in faltantes]
    motivos = []
    if ra["versao"] != rb["versao"]:
        motivos.append(f"versão do padrão difere: {ra['versao']} × {rb['versao']}")
    if ra["caminhos_sensiveis_hash"] != rb["caminhos_sensiveis_hash"]:
        motivos.append("hash da lista curada difere: as réguas mediram listas diferentes")
    return motivos


def _cobertura(laudo: dict) -> dict:
    """Cobertura de sondagem somada: caminhos executados de quantos esperados."""
    alvos = laudo.get("alvos", [])
    executado = sum(int(a.get("executado", 0)) for a in alvos)
    esperado = sum(int(a.get("esperado", 0)) for a in alvos)
    return {"executado": executado, "esperado": esperado}


def _por_severidade(laudo: dict) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for alvo in laudo.get("alvos", []):
        for f in alvo.get("findings", []):
            sev = str(f.get("severidade", "?"))
            contagem[sev] = contagem.get(sev, 0) + 1
    return dict(sorted(contagem.items()))


def _perfil(laudo: dict) -> dict:
    return {"cobertura": _cobertura(laudo),
            "por_severidade": _por_severidade(laudo),
            "alvos": len(laudo.get("alvos", []))}


def comparar(laudo_a: dict, laudo_b: dict, *, rotulo_a: str = "A",
             rotulo_b: str = "B") -> dict:
    """Compara dois laudos. `comparavel=False` (com motivos nomeados) quando as
    réguas divergem — nenhuma agregação é emitida nesse caso. Quando batem, o lado
    a lado da cobertura de sondagem e dos achados por severidade, sob a régua comum."""
    motivos = motivos_de_incompatibilidade(laudo_a, laudo_b)
    if motivos:
        return {"comparavel": False, "motivos": motivos}
    return {"comparavel": True,
            "regua": _regua(laudo_a),
            "projetos": {rotulo_a: _perfil(laudo_a), rotulo_b: _perfil(laudo_b)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("laudo_a", type=Path)
    parser.add_argument("laudo_b", type=Path)
    args = parser.parse_args(argv)
    a = json.loads(args.laudo_a.read_text(encoding="utf-8"))
    b = json.loads(args.laudo_b.read_text(encoding="utf-8"))
    resultado = comparar(a, b, rotulo_a=args.laudo_a.stem, rotulo_b=args.laudo_b.stem)
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    if not resultado["comparavel"]:
        print("INCOMPARÁVEL — réguas diferentes:", file=sys.stderr)
        for m in resultado["motivos"]:
            print(f"  - {m}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
