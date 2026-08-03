"""Harness mínimo de mutação: planta um defeito por vez e vê se a suíte morde.

Uso:  python scripts/mutar.py . webqa/escopo.py tests/test_escopo.py

Escopado de propósito: rodar mutação nos 3.073 statements do repo é caro e
inútil. O alvo é a superfície de segurança — escopo, gates, sondagem, sanitize.
Ver docs/handoff/HANDOFF-Q1-instrumentacao.md §Q5.

Score de mutação mede a força das ASSERÇÕES: quantos defeitos plantados a suíte
reprova. É outra métrica que cobertura — cobertura diz se a linha foi visitada,
mutação diz se a visita afirmou alguma coisa.

⚠️ Isto ALTERA a lógica dos gates de propósito. NUNCA rode com
WEBQA_DISCOVERY_AUTHORIZED ou WEBQA_ACTIVE_PROBES_AUTHORIZED no ambiente: um
mutante que inverta um gate rodaria a suíte inteira com o portão aberto. O
workflow de mutação limpa o ambiente explicitamente antes de chamar este script.
"""
from __future__ import annotations

import ast
import pathlib

# argv fixo, sem shell: só interpretador, pytest e caminhos deste repo entram na
# linha de comando. A justificativa fica ACIMA porque bandit lê o texto após
# `# nosec` como mais IDs de teste e reclama a cada palavra.
import subprocess  # nosec B404
import sys

CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
       ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In}


class Coletor(ast.NodeVisitor):
    """Todos os pontos mutáveis. Identidade estável: (tipo, linha, coluna, índice)."""

    def __init__(self):
        self.pontos = []

    def visit_Compare(self, n):
        for i, op in enumerate(n.ops):
            if type(op) in CMP:
                self.pontos.append(("cmp", n.lineno, n.col_offset, i))
        self.generic_visit(n)

    def visit_BoolOp(self, n):
        self.pontos.append(("bool", n.lineno, n.col_offset, 0))
        self.generic_visit(n)

    def visit_UnaryOp(self, n):
        if isinstance(n.op, ast.Not):
            self.pontos.append(("not", n.lineno, n.col_offset, 0))
        self.generic_visit(n)

    def visit_Constant(self, n):
        if isinstance(n.value, bool):
            self.pontos.append(("truth", n.lineno, n.col_offset, 0))
        elif isinstance(n.value, int | float):
            self.pontos.append(("num", n.lineno, n.col_offset, 0))
        self.generic_visit(n)


class Mutador(ast.NodeTransformer):
    def __init__(self, alvo):
        self.alvo = alvo
        self.feito = False

    def _e(self, n, k, i=0):
        return (not self.feito) and (k, n.lineno, n.col_offset, i) == self.alvo

    def visit_Compare(self, n):
        self.generic_visit(n)
        for i, op in enumerate(n.ops):
            if self._e(n, "cmp", i) and type(op) in CMP:
                n.ops[i] = CMP[type(op)]()
                self.feito = True
        return n

    def visit_BoolOp(self, n):
        self.generic_visit(n)
        if self._e(n, "bool"):
            n.op = ast.Or() if isinstance(n.op, ast.And) else ast.And()
            self.feito = True
        return n

    def visit_UnaryOp(self, n):
        self.generic_visit(n)
        if self._e(n, "not"):
            self.feito = True
            return n.operand
        return n

    def visit_Constant(self, n):
        if self._e(n, "truth"):
            self.feito = True
            return ast.Constant(not n.value)
        if self._e(n, "num"):
            self.feito = True
            return ast.Constant(n.value + 1)
        return n


def rodar(raiz, arquivo, testes):
    orig = pathlib.Path(raiz) / arquivo
    fonte = orig.read_text(encoding="utf-8")
    c = Coletor()
    c.visit(ast.parse(fonte))

    vivos, mortos, invalidos = [], 0, 0
    try:
        for p in c.pontos:
            m = Mutador(p)
            novo = m.visit(ast.parse(fonte))
            if not m.feito:
                invalidos += 1
                continue
            # Mutante que não reconstrói em fonte válida é inviável, não
            # sobrevivente: conta como inválido e segue. `Exception` amplo de
            # propósito — qualquer falha de unparse aqui é "pular este ponto".
            try:
                codigo = ast.unparse(ast.fix_missing_locations(novo))
            except Exception:  # noqa: BLE001
                invalidos += 1
                continue
            orig.write_text(codigo, encoding="utf-8")
            r = subprocess.run(  # nosec B603
                [sys.executable, "-m", "pytest", *testes, "-x", "-q", "--no-header",
                 "-p", "no:cacheprovider"],
                cwd=raiz, capture_output=True, timeout=300, check=False)
            if r.returncode == 0:
                vivos.append((p[0], p[1]))   # suíte passou COM o defeito: sobreviveu
            else:
                mortos += 1
    finally:
        orig.write_text(fonte, encoding="utf-8")   # restaura SEMPRE, inclusive em Ctrl-C
    return len(c.pontos), mortos, vivos, invalidos


if __name__ == "__main__":
    raiz, arquivo, *testes = sys.argv[1:]
    n, mortos, vivos, inv = rodar(raiz, arquivo, testes)
    viaveis = mortos + len(vivos)
    print(f"\n{arquivo}: {n} pontos, {viaveis} viáveis, {mortos} mortos, "
          f"{len(vivos)} SOBREVIVERAM → score {100 * mortos / max(viaveis, 1):.1f}%")
    for k, linha in vivos:
        print(f"   sobreviveu: {arquivo}:{linha}  ({k})")
    raise SystemExit(1 if vivos else 0)
