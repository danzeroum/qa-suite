"""Telemetria operacional — o que várias campanhas dizem sobre a PRÓPRIA suíte.

Ver `docs/TELEMETRIA.md`. Agrega artefatos que **já existem** (`summary.json` de
cada execução de campanha) para responder três perguntas que uma execução só não
responde:

1. **quais testes custam caro** — mediana de `duration_s` por teste;
2. **quais testes flakeiam** — alternância de veredito contra o MESMO alvo;
3. **quais checks são suspeitos** — `failed` em alvo maduro é candidato a falso
   positivo; `passed` em absolutamente tudo é candidato a check morto.

**Não coleta nada novo.** Nenhuma requisição, nenhum campo a mais no
`summary.json`, nenhum acesso a corpo de resposta. Lê chaves agregadas do que a
suíte já gravou e conta.

Duas linhas que este módulo não cruza:

* **nunca dado pessoal.** `detail` já nasce sanitizado na borda de escrita e nem
  é lido aqui — a telemetria opera sobre `test`, `dimension`, `estado` e
  `duration_s`. Corpo de resposta, PII e IP não passam por aqui em nenhum caminho;
* **nunca alvo nominal em artefato versionável.** `report/telemetria.json` é
  local e ignorado pelo git, então guarda o host por extenso porque é ele que o
  operador precisa ler. Qualquer saída que possa ser versionada ou publicada
  passa por `anonimizar_agregado`, que troca o nome pelo `sha256` — a mesma
  decisão que o ledger de estabilidade já tomou.

Percentis por `statistics.quantiles`. Nada de `numpy`/`pandas`: a suíte inteira
é stdlib-first, e uma dependência científica para calcular p75 seria o oposto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:                       # execução direta
    sys.path.insert(0, str(RAIZ))

REPORT_DIR = Path(os.environ.get("WEBQA_REPORT_DIR") or RAIZ / "report")
CAMPANHA_PADRAO = REPORT_DIR / "campanha"
SAIDA_PADRAO = REPORT_DIR / "telemetria.json"

# Estados que contam como "a suíte deu um veredito" e "a suíte não deu".
# `skipped` e `xfail` ficam de FORA da conta de flake de propósito: pular por
# ausência de formulário na página não é instabilidade, é o alvo sendo diferente.
ESTADO_OK = "passed"
ESTADOS_RUINS = ("failed", "error")

# Folga sobre o p75 na sugestão de threshold. Não é número mágico: um limiar
# colado no p75 reprova um quarto das execuções saudáveis, e um limiar folgado
# demais não reprova nada. 20% é o bastante para absorver variação de rede sem
# transformar o orçamento em decoração.
FOLGA_CALIBRACAO = 1.20

# Métricas calibráveis e o threshold de config.yaml correspondente. Tabela
# explícita porque nem toda métrica medida vira limiar — e um mapeamento
# implícito por prefixo erraria em silêncio no dia em que os nomes divergirem.
CALIBRAVEIS = (
    ("ttfb_ms", "ttfb_ms", 0),
    ("total_ms", "p95_ms", 0),
    ("lcp_ms", "lcp_ms", 0),
    ("cls", "cls", 3),
    ("page_kb", "page_weight_kb", 0),
)


def sha_do_alvo(alvo: str) -> str:
    """Mesma derivação do ledger (`scripts/estabilidade.py`).

    O digest é chave de agrupamento, não segredo: o espaço de URLs é pequeno e
    enumerável. O que ele garante é que o agregado anônimo não CARREGA o nome.
    """
    return hashlib.sha256((alvo or "").encode("utf-8")).hexdigest()


def carregar_summaries(raiz: Path) -> list[dict]:
    """Todo `summary.json` sob a raiz, com a origem anotada em cada um.

    A origem viaja junto porque um número sem procedência não é auditável: quem
    ler "mediana 4,2 s" precisa poder voltar ao arquivo que a produziu.
    """
    summaries = []
    for caminho in sorted(raiz.rglob("summary.json")):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                      # artefato truncado não derruba a conta
        if not isinstance(dados, dict) or "results" not in dados:
            continue
        dados["_origem"] = str(caminho.relative_to(raiz))
        summaries.append(dados)
    return summaries


def _estado(resultado: dict) -> str:
    return resultado.get("estado") or resultado.get("outcome") or "skipped"


def _percentis(amostras: list[float]) -> dict:
    """Mediana, p75 e p95. Amostra única não vira percentil inventado."""
    limpas = sorted(float(a) for a in amostras if a is not None)
    if not limpas:
        return {}
    if len(limpas) < 4:
        # `quantiles` exige n≥2 e fica sem sentido com 2 ou 3 pontos. Dizer
        # "p95 de duas amostras" seria dar precisão que o dado não tem.
        return {"mediana": round(statistics.median(limpas), 3),
                "pior": round(limpas[-1], 3), "n": len(limpas)}
    q = statistics.quantiles(limpas, n=100, method="inclusive")
    return {"mediana": round(statistics.median(limpas), 3),
            "p75": round(q[74], 3), "p95": round(q[94], 3),
            "pior": round(limpas[-1], 3), "n": len(limpas)}


# ---------------------------------------------------------------- cortes

def ranking_de_lentos(summaries: list[dict], limite: int = 15) -> list[dict]:
    """Corte 1: quanto custa medir, por teste, ranqueado pela mediana."""
    duracoes: dict[str, list[float]] = defaultdict(list)
    for s in summaries:
        for r in s.get("results", []):
            if r.get("duration_s") is not None:
                duracoes[str(r.get("test", "?"))].append(float(r["duration_s"]))
    ranking = [{"test": teste, **_percentis(amostras)}
               for teste, amostras in duracoes.items() if amostras]
    ranking.sort(key=lambda t: t.get("mediana", 0.0), reverse=True)
    return ranking[:limite]


def flake_por_teste(summaries: list[dict]) -> list[dict]:
    """Corte 2: alternância de veredito contra o MESMO alvo.

    Alvo diferente NÃO conta como flake — é comportamento do alvo, não da suíte.
    É a mesma distinção que dá sentido ao ledger de estabilidade: um site que
    reprova e outro que passa não são a suíte oscilando.

    E flake exige ALTERNÂNCIA, não incidente: um `error` isolado, sem nenhuma
    execução `passed` do mesmo teste contra o mesmo alvo, é uma falha — pode ser
    infraestrutura, pode ser o alvo — mas não é instabilidade. Chamar tudo de
    flake faria a métrica perder a única coisa que ela sabe dizer.
    """
    por_par: dict[tuple[str, str], list[str]] = defaultdict(list)
    for s in summaries:
        sha = sha_do_alvo(str(s.get("alvo") or ""))
        for r in s.get("results", []):
            por_par[(str(r.get("test", "?")), sha)].append(_estado(r))

    achados = []
    for (teste, sha), estados in por_par.items():
        if len(estados) < 2:
            continue
        contagem = Counter(estados)
        bons = contagem[ESTADO_OK]
        ruins = sum(contagem[e] for e in ESTADOS_RUINS)
        if not (bons and ruins):
            continue                       # sem alternância: não é flake
        achados.append({
            "test": teste,
            "alvo_sha256": sha,
            "execucoes": len(estados),
            "passed": bons,
            "falhou": ruins,
            "placar": " ".join(f"{n}×{e}" for e, n in sorted(contagem.items())),
            # Fração das execuções em que o veredito divergiu do majoritário.
            "instabilidade": round(min(bons, ruins) / len(estados), 3),
        })
    achados.sort(key=lambda a: (a["instabilidade"], a["execucoes"]), reverse=True)
    return achados


def distribuicao_por_check(summaries: list[dict]) -> list[dict]:
    """Corte 3: como cada check se comporta ENTRE alvos.

    Duas suspeitas saem daqui, e nenhuma é veredito — são candidatos a olhar:

    * check que reprova em alvo maduro é **candidato a falso positivo** da
      suíte, que é exatamente o papel do alvo `falso-positivo` na campanha;
    * check que passa em absolutamente todo alvo é **candidato a check morto**:
      pode estar certo, pode ter parado de detectar. O contrato do fixture
      responde essa segunda pergunta; aqui só se levanta a suspeita.
    """
    por_check: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    dimensao: dict[str, str] = {}
    for s in summaries:
        sha = sha_do_alvo(str(s.get("alvo") or ""))
        for r in s.get("results", []):
            teste = str(r.get("test", "?"))
            por_check[teste][sha][_estado(r)] += 1
            dimensao.setdefault(teste, str(r.get("dimension") or "other"))

    linhas = []
    for teste, por_alvo in por_check.items():
        estados_por_alvo = {sha: max(c, key=c.get) for sha, c in por_alvo.items()}
        veredito = Counter(estados_por_alvo.values())
        alvos = len(estados_por_alvo)
        linhas.append({
            "test": teste,
            "dimension": dimensao.get(teste, "other"),
            "alvos": alvos,
            "por_estado": dict(sorted(veredito.items())),
            "reprovou_em": veredito.get("failed", 0),
            # Só é "candidato a check morto" com base suficiente: passar em dois
            # alvos não é evidência de nada.
            "candidato_a_check_morto": alvos >= 3 and veredito.get(ESTADO_OK, 0) == alvos,
            "candidato_a_falso_positivo": veredito.get("failed", 0) > 0,
        })
    linhas.sort(key=lambda linha: (linha["reprovou_em"], linha["alvos"]), reverse=True)
    return linhas


def metricas_agregadas(summaries: list[dict]) -> dict:
    """Distribuição das métricas do alvo, por alvo. Ausente NÃO vira zero."""
    por_alvo: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for s in summaries:
        sha = sha_do_alvo(str(s.get("alvo") or ""))
        for chave, valor in (s.get("metricas") or {}).items():
            if valor is not None:
                por_alvo[sha][chave].append(float(valor))
    return {sha: {chave: _percentis(v) for chave, v in metricas.items() if v}
            for sha, metricas in por_alvo.items()}


# ---------------------------------------------------------------- saída

def agregar(summaries: list[dict]) -> dict:
    """Agregado NOMINAL — para `report/`, que é local e ignorado pelo git."""
    alvos = {}
    for s in summaries:
        nome = str(s.get("alvo") or "")
        alvos[sha_do_alvo(nome)] = nome
    return {
        "execucoes": len(summaries),
        "alvos": [{"alvo": nome, "alvo_sha256": sha} for sha, nome in sorted(alvos.items())],
        "origens": sorted(str(s.get("_origem", "?")) for s in summaries),
        "ranking_de_lentos": ranking_de_lentos(summaries),
        "flake": flake_por_teste(summaries),
        "distribuicao_por_check": distribuicao_por_check(summaries),
        "metricas": metricas_agregadas(summaries),
    }


def anonimizar_agregado(dados: dict) -> dict:
    """Remove toda identificação NOMINAL de alvo. Obrigatório antes de versionar.

    O `alvo_sha256` fica: ele agrupa sem nomear, que é o que um agregado
    multi-site precisa. O nome do host sai, e sai por remoção — não por
    mascaramento parcial, que é reversível para quem conhece o conjunto de
    alvos (são três, listados num yaml público).

    Também sai `origens`: o caminho do artefato carrega o host no nome do
    diretório (`report/campanha/www.mozilla.org/run1/`), e um campo de
    rastreabilidade que reintroduz o nome anularia o resto.
    """
    limpo = dict(dados)
    limpo["alvos"] = [{"alvo_sha256": a["alvo_sha256"]}
                      for a in dados.get("alvos", []) if a.get("alvo_sha256")]
    limpo.pop("origens", None)
    limpo["anonimizado"] = True
    return limpo


def _thresholds_atuais() -> dict:
    """Limiares vigentes, para o diff ter os dois lados. `{}` quando indisponível.

    Reusa a resolução oficial (`config.yaml` + env) em vez de reimplementá-la:
    duas leituras do mesmo arquivo divergem, e divergiriam justamente no número
    que o diff apresenta como "atual". Ausência de config não é erro aqui — a
    sugestão simplesmente sai sem o lado esquerdo.
    """
    try:
        from webqa.config import load_settings

        return dict(load_settings().thresholds)
    except Exception:
        return {}


def sugerir_thresholds(dados: dict) -> list[str]:
    """Diff COMENTADO de limiares, para leitura humana. Nunca escreve nada.

    A guarda que importa é esta: um processo que ajusta o próprio limiar a
    partir do que mediu converge para aprovar tudo. Ele mede um alvo lento,
    afrouxa o orçamento, e da próxima vez o alvo lento passa. A sugestão sai em
    texto justamente para obrigar um humano a decidir se o alvo melhora ou se o
    orçamento estava errado — são coisas diferentes, e só quem conhece o produto
    sabe qual é.
    """
    atuais = _thresholds_atuais()
    linhas = ["# Sugestão de limiares a partir do p75 observado + folga de "
              f"{round((FOLGA_CALIBRACAO - 1) * 100)}%.",
              "# NADA foi escrito: revise e edite config.yaml à mão, se concordar.",
              "# Limiar que se ajusta sozinho ao que mediu converge para aprovar tudo.",
              ""]
    houve = False
    for chave_metrica, chave_threshold, casas in CALIBRAVEIS:
        amostras = [m.get(chave_metrica, {}).get("p75")
                    for m in dados.get("metricas", {}).values()]
        validas = [a for a in amostras if a is not None]
        if not validas:
            linhas.append(f"# {chave_threshold}: sem amostra suficiente (p75 exige "
                          "4+ execuções) — mantido como está")
            continue
        houve = True
        sugerido = round(max(validas) * FOLGA_CALIBRACAO, casas)
        sugerido = int(sugerido) if casas == 0 else sugerido
        atual = atuais.get(chave_threshold)
        if atual is None:
            linhas.append(f"+   {chave_threshold}: {sugerido}   # não declarado hoje")
        elif float(atual) == float(sugerido):
            linhas.append(f"    {chave_threshold}: {atual}   # já calibrado")
        else:
            direcao = "afrouxar" if float(sugerido) > float(atual) else "apertar"
            linhas.append(f"-   {chave_threshold}: {atual}")
            linhas.append(f"+   {chave_threshold}: {sugerido}   # {direcao}; "
                          f"p75 observado × {FOLGA_CALIBRACAO:g}")
    if not houve:
        linhas.append("")
        linhas.append("# Nenhuma métrica com amostra suficiente. Rode mais campanhas.")
    return linhas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--campanha", type=Path, default=CAMPANHA_PADRAO,
                        help="raiz das execuções de campanha (default: report/campanha)")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--anonimo", action="store_true",
                        help="grava o agregado SEM identificação nominal de alvo — "
                             "é o único que pode ser versionado ou publicado")
    parser.add_argument("--calibrar", action="store_true",
                        help="imprime sugestão de limiares; NUNCA escreve no config.yaml")
    args = parser.parse_args(argv)

    if not args.campanha.exists():
        print(f"telemetria: {args.campanha} não existe — rode `make campanha` antes.",
              file=sys.stderr)
        return 1

    summaries = carregar_summaries(args.campanha)
    if not summaries:
        print(f"telemetria: nenhum summary.json sob {args.campanha} — "
              "rode `make campanha` antes.", file=sys.stderr)
        return 1

    dados = agregar(summaries)
    if args.anonimo:
        dados = anonimizar_agregado(dados)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(dados, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print(f"telemetria: {args.saida} · {dados['execucoes']} execução(ões) · "
          f"{len(dados['flake'])} teste(s) com alternância de veredito")

    if args.calibrar:
        print()
        for linha in sugerir_thresholds(dados):
            print(linha)
    return 0


if __name__ == "__main__":                          # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
