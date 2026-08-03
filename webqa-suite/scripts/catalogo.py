"""Catálogo de testes por leitura ESTÁTICA (AST) — o inventário que o cockpit lê.

Lê `checks/` e `tests/` sem importar módulo, sem executar nada, sem saber qual
framework o projeto usa (Trabalho B da arquitetura padrão-em-harness: agnóstico,
roda em qualquer repositório). Reconcilia com a última execução (`report/
summary.json`) quando existe — ausência de run vira estado `nao-executado`
NOMEADO, nunca zero.

Duas populações que NUNCA se somam (§2 do plano): `checks/` julga o alvo (`alvo`),
`tests/` verifica a suíte (`suite`). O catálogo é a população; o run é a amostra.

Uso:
    python scripts/catalogo.py --json            # emite o catálogo em JSON
    python scripts/catalogo.py --json --raiz .   # raiz explícita

Somente stdlib.
"""
from __future__ import annotations

import argparse
import ast
import json
import statistics
from pathlib import Path

# Marcadores que são DIMENSÃO de qualidade (viram coluna em "Dimensões"). Tudo
# menos `browser`, que é atributo de capacidade (exige navegador), não dimensão.
# `verification` é dimensão E atributo — verifica a suíte e descreve a população.
_ATRIBUTOS = ("browser", "verification")

# Marks EMBUTIDOS do pytest não são dimensão: `parametrize` vira `casos`,
# `xfail`/`skipif` viram campos próprios. Excluí-los mantém "Dimensões" com os
# markers reais do pytest.ini — sem que o gerador precise conhecer a lista (um
# marker novo aparece sozinho; ver teste de OS-27).
_MARKS_EMBUTIDOS = frozenset({"parametrize", "skipif", "xfail", "usefixtures",
                              "filterwarnings", "skip"})

RAIZ_PADRAO = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------- descoberta
def _arquivos_de_teste(raiz: Path) -> list[Path]:
    """`test_*.py` de checks/ e tests/, mais os `.feature` do Gherkin."""
    achados: list[Path] = []
    for base in ("checks", "tests"):
        dir_ = raiz / base
        if dir_.is_dir():
            achados += sorted(dir_.rglob("test_*.py"))
            achados += sorted(dir_.rglob("*.feature"))
    return achados


def _populacao(rel: str) -> str:
    """checks/ mede o ALVO; tests/ verifica a SUÍTE. Nunca se somam."""
    return "alvo" if rel.startswith("checks/") else "suite"


def _nivel(rel: str, dimensoes: set[str], atributos: set[str]) -> str:
    """Nível derivado de evidência no código, em ordem de precedência:
    aceitação (marker acceptance) → sistema (browser/load) → integração (arquivo
    em checks/) → unidade (o resto). Ver §2.1 do plano consolidado."""
    if "acceptance" in dimensoes:
        return "aceitacao"
    if "browser" in atributos or "load" in dimensoes:
        return "sistema"
    if rel.startswith("checks/"):
        return "integracao"
    return "unidade"


# ------------------------------------------------------------ leitura por AST
def _markers_da_funcao(no: ast.FunctionDef, markers_modulo: list[str]) -> list[str]:
    """Markers do teste em ORDEM de declaração: os do módulo (pytestmark) e depois
    os decorados na função, de cima para baixo. Deduplicado preservando a ordem —
    é a ordem que o laudo mostra em Dimensões, não alfabética."""
    marks = list(markers_modulo)
    for dec in no.decorator_list:
        m = _mark_de_decorator(dec)
        if m:
            marks.append(m)
    return list(dict.fromkeys(marks))


def _mark_de_decorator(dec: ast.expr) -> str | None:
    """Nome de `pytest.mark.X` (com ou sem chamada); `None` para o resto."""
    alvo = dec.func if isinstance(dec, ast.Call) else dec
    if (isinstance(alvo, ast.Attribute) and isinstance(alvo.value, ast.Attribute)
            and alvo.value.attr == "mark"):
        return alvo.attr
    return None


def _pytestmark_do_modulo(arvore: ast.Module) -> list[str]:
    """Markers de `pytestmark = ...` no módulo (valor único ou lista), em ordem."""
    marks: list[str] = []
    for no in arvore.body:
        if not isinstance(no, ast.Assign):
            continue
        if not any(isinstance(a, ast.Name) and a.id == "pytestmark" for a in no.targets):
            continue
        valores = no.value.elts if isinstance(no.value, ast.List | ast.Tuple) else [no.value]
        for v in valores:
            m = _mark_de_decorator(v)
            if m:
                marks.append(m)
    return marks


def _casos_de(no: ast.FunctionDef) -> int:
    """Casos coletáveis: produto dos tamanhos de cada `@parametrize`. Sem
    parametrização, 1 — um teste é um caso."""
    total = 1
    for dec in no.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        alvo = dec.func
        if isinstance(alvo, ast.Attribute) and alvo.attr == "parametrize" and dec.args:
            valores = dec.args[-1]
            if isinstance(valores, ast.List | ast.Tuple):
                total *= max(1, len(valores.elts))
    return total


def _tem_marker(no: ast.FunctionDef, nome: str, *, strict: bool = False) -> bool:
    """A função tem `@pytest.mark.<nome>` (e, se strict, com strict=True)?"""
    for dec in no.decorator_list:
        chamada = dec if isinstance(dec, ast.Call) else None
        alvo = chamada.func if chamada else dec
        if not (isinstance(alvo, ast.Attribute) and alvo.attr == nome):
            continue
        if not strict:
            return True
        for kw in (chamada.keywords if chamada else []):
            if kw.arg == "strict" and isinstance(kw.value, ast.Constant) and kw.value.value:
                return True
    return False


def _conta_xfail_no_corpo(no: ast.FunctionDef) -> int:
    """Chamadas a `pytest.xfail(...)` DENTRO do corpo — veredito condicional em
    runtime (o teste decide se é xfail ao rodar), distinto do marker estático."""
    total = 0
    for sub in ast.walk(no):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                and sub.func.attr == "xfail":
            total += 1
    return total


def _garante(no: ast.FunctionDef) -> str:
    """Primeira linha do docstring — o contrato escrito do teste, se houver."""
    doc = ast.get_docstring(no, clean=True)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _testes_do_py(caminho: Path, rel: str) -> list[dict]:
    """Todos os `test_*` de um arquivo Python, já classificados."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    markers_mod = _pytestmark_do_modulo(arvore)
    testes = []
    for no in arvore.body:
        if not (isinstance(no, ast.FunctionDef) and no.name.startswith("test_")):
            continue
        markers = [m for m in _markers_da_funcao(no, markers_mod)
                   if m not in _MARKS_EMBUTIDOS]
        dimensoes = [m for m in markers if m != "browser"]      # ordem de declaração
        atributos = sorted(m for m in markers if m in _ATRIBUTOS)
        testes.append({
            "nodeid": f"{rel}::{no.name}",
            "arquivo": rel, "funcao": no.name, "linha": no.lineno,
            "populacao": _populacao(rel),
            "nivel": _nivel(rel, set(dimensoes), set(atributos)),
            "dimensoes": dimensoes, "atributos": atributos,
            "casos": _casos_de(no),
            "xfail": _tem_marker(no, "xfail"),
            "xfail_strict": _tem_marker(no, "xfail", strict=True),
            "skipif": _tem_marker(no, "skipif"),
            "veredito_condicional": _conta_xfail_no_corpo(no),
            "origem": "ast",
            "garante": _garante(no),
        })
    return testes


def _cenarios_do_feature(caminho: Path, rel: str) -> list[dict]:
    """Cenários Gherkin (`Cenário:`/`Scenario:`) — invisíveis ao AST de Python."""
    testes = []
    for i, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        texto = linha.strip()
        for prefixo in ("Cenário:", "Cenario:", "Scenario:"):
            if texto.startswith(prefixo):
                nome = texto[len(prefixo):].strip()
                testes.append({
                    "nodeid": f"{rel}::{nome}", "arquivo": rel, "funcao": nome,
                    "linha": i, "populacao": _populacao(rel),
                    "nivel": "aceitacao", "dimensoes": ["acceptance"], "atributos": [],
                    "casos": 1, "xfail": False, "xfail_strict": False, "skipif": False,
                    "veredito_condicional": 0, "origem": "gherkin", "garante": nome,
                })
    return testes


def catalogar(raiz: Path) -> list[dict]:
    """Lista de testes de todo o repositório, ordenada por nodeid."""
    testes: list[dict] = []
    for caminho in _arquivos_de_teste(raiz):
        rel = caminho.relative_to(raiz).as_posix()
        if caminho.suffix == ".feature":
            testes += _cenarios_do_feature(caminho, rel)
        else:
            testes += _testes_do_py(caminho, rel)
    return sorted(testes, key=lambda t: t["nodeid"])


# ----------------------------------------------------- reconciliação com o run
def _resultados_do_run(raiz: Path) -> dict[str, dict]:
    """{nodeid: {outcome, duration}} do último `report/summary.json`, se existe."""
    caminho = raiz / "report" / "summary.json"
    if not caminho.exists():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {r["test"]: r for r in dados.get("results", [])}


def _reconciliar(testes: list[dict], resultados: dict[str, dict]) -> list[str]:
    """Carimba `estado`/`duracao_s` em cada teste a partir do run. Devolve os
    órfãos: resultados de testes que não existem mais no catálogo (renomeados
    ou apagados) — nunca somem em silêncio."""
    for t in testes:
        r = resultados.get(t["nodeid"])
        if r is None:
            t["estado"], t["duracao_s"] = "nao-executado", 0.0
        else:
            t["estado"] = str(r.get("outcome", "nao-executado"))
            t["duracao_s"] = float(r.get("duration", 0.0) or 0.0)
    conhecidos = {t["nodeid"] for t in testes}
    return sorted(n for n in resultados if n not in conhecidos)


# --------------------------------------------------------------- agregados
def _descritiva(duracoes: list[float]) -> dict:
    """Estatística descritiva de durações, com outliers por Tukey (Q3+1,5·IQR).
    Vazio quando não houve execução — dict vazio, nunca zeros que enganam."""
    validas = [d for d in duracoes if d > 0]
    if not validas:
        return {}
    ordenadas = sorted(validas)
    n = len(ordenadas)
    limite = _limite_tukey(ordenadas)
    return {
        "n": n,
        "mediana": round(statistics.median(ordenadas), 3),
        "media": round(statistics.fmean(ordenadas), 3),
        "p95": round(_percentil(ordenadas, 95), 3),
        "desvio": round(statistics.pstdev(ordenadas), 3) if n > 1 else 0.0,
        "limite_outlier": round(limite, 3),
        "outliers": sum(1 for d in ordenadas if d > limite),
        "total_s": round(sum(ordenadas), 3),
    }


def _percentil(ordenadas: list[float], p: float) -> float:
    if len(ordenadas) == 1:
        return ordenadas[0]
    pos = (p / 100) * (len(ordenadas) - 1)
    baixo = int(pos)
    frac = pos - baixo
    if baixo + 1 >= len(ordenadas):
        return ordenadas[-1]
    return ordenadas[baixo] + frac * (ordenadas[baixo + 1] - ordenadas[baixo])


def _limite_tukey(ordenadas: list[float]) -> float:
    q1 = _percentil(ordenadas, 25)
    q3 = _percentil(ordenadas, 75)
    return q3 + 1.5 * (q3 - q1)


def _contar(testes: list[dict], chave) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for t in testes:
        contagem[chave(t)] = contagem.get(chave(t), 0) + 1
    return dict(sorted(contagem.items()))


def _por_grupo(testes: list[dict], grupos) -> dict[str, dict]:
    """Por grupo (dimensão ou arquivo): contagem por estado + total."""
    saida: dict[str, dict] = {}
    for t in testes:
        for g in grupos(t):
            bloco = saida.setdefault(g, {})
            bloco[t["estado"]] = bloco.get(t["estado"], 0) + 1
            bloco["total"] = bloco.get("total", 0) + 1
    return {g: dict(sorted(saida[g].items())) for g in sorted(saida)}


def _duracoes_executadas(pop: list[dict]) -> list[float]:
    return [t["duracao_s"] for t in pop if t["estado"] != "nao-executado"]


def _agregar(testes: list[dict]) -> dict:
    alvo = [t for t in testes if t["populacao"] == "alvo"]
    suite = [t for t in testes if t["populacao"] == "suite"]
    return {
        "populacoes": {"alvo": len(alvo), "suite": len(suite)},
        "niveis": _contar(testes, lambda t: t["nivel"]),
        "estados": _contar(testes, lambda t: t["estado"]),
        "por_dimensao": _por_grupo(testes, lambda t: t["dimensoes"] or ["sem-dimensao"]),
        "por_arquivo": _por_grupo(testes, lambda t: [t["arquivo"]]),
        "duracao_suite": _descritiva(_duracoes_executadas(suite)),
        "duracao_alvo": _descritiva(_duracoes_executadas(alvo)),
        "casos": sum(t["casos"] for t in testes),
        "condicionais": sum(t["veredito_condicional"] for t in testes),
        "gherkin": sum(1 for t in testes if t["origem"] == "gherkin"),
        "sem_contrato": sum(1 for t in testes if not t["garante"]),
    }


# --------------------------------------------------------------- procedência
def _procedencia(raiz: Path) -> dict:
    """Carimbo de qual leitura produziu o catálogo. Lê `.git` sem subprocess:
    campos vazios quando não é um checkout — nunca inventa commit."""
    git = raiz / ".git"
    commit = ramo = assunto = ""
    head = git / "HEAD"
    if head.exists():
        conteudo = head.read_text(encoding="utf-8").strip()
        if conteudo.startswith("ref:"):
            ref = conteudo[4:].strip()
            ramo = ref.rsplit("/", 1)[-1]
            ref_file = git / ref
            if ref_file.exists():
                commit = ref_file.read_text(encoding="utf-8").strip()[:7]
        else:
            commit = conteudo[:7]
    return {"repositorio": "", "commit": commit, "assunto": assunto, "ramo": ramo}


def montar_catalogo(raiz: Path) -> dict:
    """Catálogo completo de UMA leitura: procedência, agregados, reconciliação,
    testes. É a fonte única que o cockpit veste de HTML."""
    testes = catalogar(raiz)
    resultados = _resultados_do_run(raiz)
    orfaos = _reconciliar(testes, resultados)
    executados = sum(1 for t in testes if t["estado"] != "nao-executado")
    return {
        "procedencia": _procedencia(raiz),
        "agregados": _agregar(testes),
        "reconciliacao": {
            "executados": executados,
            "nunca_vistos": len(testes) - executados,
            "orfaos": orfaos,
        },
        "testes": testes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO)
    parser.add_argument("--json", action="store_true", help="emite o catálogo em JSON no stdout")
    args = parser.parse_args(argv)
    catalogo = montar_catalogo(args.raiz)
    if args.json:
        print(json.dumps(catalogo, ensure_ascii=False, indent=1))
        return 0
    ag = catalogo["agregados"]
    print(f"{len(catalogo['testes'])} testes / {ag['casos']} casos "
          f"({ag['populacoes']['alvo']} alvo, {ag['populacoes']['suite']} suíte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
