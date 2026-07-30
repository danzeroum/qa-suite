#!/usr/bin/env python3
"""Campanha: a suíte inteira, passiva, contra alvos reais, N vezes, consolidada.

Este é o **nível sistema** da suíte. Os testes de `tests/` verificam unidades; a
campanha valida o conjunto contra a realidade — alvos que ninguém controla, que
mudam de resposta entre duas requisições e que às vezes simplesmente recusam
atender. É onde se descobre o que nenhum fixture fabricado revela.

Dois eixos de TEMPO, que não devem ser confundidos:

* **tempo do alvo** — TTFB, total, FCP, LCP, CLS: o que o usuário do alvo sente;
* **tempo da suíte** — quanto custa medir aquilo. Suíte que leva 4 minutos por
  alvo não roda a cada commit, e uma suíte que não roda não protege nada.

E dois eixos de RESULTADO:

* **veredito** — passed/failed/xfail/skipped por dimensão;
* **estabilidade do veredito entre repetições** — o eixo que só existe porque
  repetimos. Um teste que dá 2×passed 1×failed não tem média: tem um problema.
  A mediana esconderia exatamente isso, então instabilidade é marcada, nunca
  agregada.

Pelo mesmo motivo, toda métrica sai em **mediana E pior caso**. O pior caso é o
que o usuário azarado viveu; a mediana sozinha é a estatística que faz um alvo
intermitente parecer saudável.

Somente stdlib + PyYAML + httpx (já dependências da suíte).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics

# Roda pytest com argv fixo e sem shell; nada do alvo entra na linha de comando.
# A justificativa fica ACIMA porque bandit lê o que vem depois de `# nosec` como
# mais IDs de teste e avisa a cada palavra.
import subprocess  # nosec B404
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CAMPANHA_PADRAO = RAIZ / "campanha.yaml"
SAIDA_PADRAO = RAIZ / "report" / "campanha"

# A campanha é PASSIVA por definição. Não basta não pedir carga: se o ambiente
# já traz a autorização de carga, alguma outra intenção está em jogo, e testes
# marcados `load` deixariam de se auto-pular. Abortar é mais honesto que rodar
# uma campanha que o operador acha passiva e não é.
ENV_CARGA = "WEBQA_LOAD_AUTHORIZED"
SELECAO = "not load and not verification"

# Métricas do alvo, na ordem em que entram no consolidado. Todas são
# "pior quando maior" — é o que autoriza `max()` como pior caso. Se algum dia
# entrar métrica onde maior é melhor (taxa de acerto de cache, por exemplo),
# esta tabela precisa ganhar a direção junto com o rótulo.
METRICAS = (
    ("ttfb_ms", "TTFB (ms)"),
    ("total_ms", "Download total (ms)"),
    ("fcp_ms", "FCP (ms)"),
    ("lcp_ms", "LCP (ms)"),
    ("cls", "CLS"),
    ("dcl_ms", "DOMContentLoaded (ms)"),
    ("page_kb", "Peso da página (KB)"),
)
ESTADOS = ("passed", "failed", "xfail", "skipped", "error")
# Do melhor ao pior. Um teste pode render mais de uma entrada na mesma execução
# (o corpo passou, o teardown estourou); o desfecho DAQUELA execução é o pior
# deles. Colapsar pelo melhor esconderia infraestrutura quebrada, e contar as
# duas entradas inventaria instabilidade onde houve um teste só.
SEVERIDADE = ("passed", "skipped", "xfail", "failed", "error")
TOP_LENTOS = 5


class CampanhaAbortada(RuntimeError):
    """Erro de operação: a campanha não deve nem começar."""


@dataclass(frozen=True)
class Alvo:
    url: str
    papel: str
    crawl_max_pages: int = 5
    user_agent: str | None = None

    @property
    def host(self) -> str:
        """Host puro, usado como diretório. Sem porta e sem esquema: o nome do
        diretório é rótulo de leitura humana, não identidade criptográfica."""
        return urlparse(self.url).hostname or "alvo"


@dataclass(frozen=True)
class Campanha:
    alvos: tuple[Alvo, ...]
    repeticoes: int = 3
    pausa_s: float = 10.0


@dataclass
class ResultadoAlvo:
    """O que a campanha observou de UM alvo — acessível ou não."""

    alvo: Alvo
    acessivel: bool = True
    motivo: str = ""
    execucoes: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- guardas

def verificar_ambiente_passivo(ambiente: dict[str, str] | None = None) -> None:
    """Aborta ANTES de qualquer requisição se o ambiente autorizar carga.

    Checa presença, não valor: `WEBQA_LOAD_AUTHORIZED=0` também aborta. Quem
    exportou a variável para valer sabe desexportá-la; quem a deixou pela metade
    não deveria descobrir o efeito no meio de nove execuções contra alvo alheio.
    """
    ambiente = os.environ if ambiente is None else ambiente
    if ENV_CARGA in ambiente:
        raise CampanhaAbortada(
            f"campanha é passiva: {ENV_CARGA} está setado no ambiente "
            f"(valor irrelevante). Rode `unset {ENV_CARGA}` e repita. "
            "Para carga autorizada existe `pytest -m load`, que é outra coisa."
        )


# ---------------------------------------------------------------- entrada

def carregar_campanha(caminho: Path) -> Campanha:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    alvos = []
    for item in dados.get("alvos") or []:
        url = str(item.get("url", "")).rstrip("/")
        if not url:
            continue
        alvos.append(
            Alvo(
                url=url,
                papel=str(item.get("papel", "")),
                crawl_max_pages=int(item.get("crawl_max_pages", 5)),
                user_agent=(str(item["user_agent"]) if item.get("user_agent") else None),
            )
        )
    if not alvos:
        raise CampanhaAbortada(f"{caminho} não declara nenhum alvo utilizável.")
    return Campanha(
        alvos=tuple(alvos),
        repeticoes=max(1, int(dados.get("repeticoes", 3))),
        # Piso, não default: reduzir a pausa por configuração transformaria a
        # campanha em rajada acidental contra alvo de terceiro.
        pausa_s=max(10.0, float(dados.get("pausa_s", 10))),
    )


# ---------------------------------------------------------------- execução

def preflight_http(alvo: Alvo, timeout_s: float = 20.0) -> tuple[bool, str]:
    """Uma requisição para saber se vale gastar uma execução inteira no alvo.

    Alvo fora do ar (ou que recusa o cliente) faria as ~90 asserções da suíte
    falharem em cascata por um motivo só, produzindo um relatório que fala do
    alvo quando deveria falar da rede. Melhor uma pergunta antes.
    """
    import httpx

    cabecalhos = {"User-Agent": alvo.user_agent} if alvo.user_agent else None
    try:
        resposta = httpx.get(alvo.url, timeout=timeout_s, follow_redirects=True,
                             headers=cabecalhos)
    except Exception as erro:      # rede, DNS, TLS, proxy: tudo é inacessível
        return False, f"{type(erro).__name__}: {str(erro)[:160]}"
    if resposta.status_code >= 400:
        return False, f"HTTP {resposta.status_code} na home"
    return True, f"HTTP {resposta.status_code}"


def env_da_execucao(alvo: Alvo, destino: Path,
                    base: dict[str, str] | None = None) -> dict[str, str]:
    """Ambiente de UMA execução: alvo, saída isolada e crawl reduzido.

    `WEBQA_REPORT_DIR` por alvo×repetição é o que impede a execução seguinte de
    sobrescrever o summary.json da anterior — sem isso não há amostra, e sem
    amostra não há mediana nem instabilidade.
    """
    ambiente = dict(os.environ if base is None else base)
    ambiente.update({
        "WEBQA_TARGET_URL": alvo.url,
        "WEBQA_REPORT_DIR": str(destino),
        "WEBQA_CRAWL_MAX_PAGES": str(alvo.crawl_max_pages),
    })
    if alvo.user_agent:
        ambiente["WEBQA_USER_AGENT"] = alvo.user_agent
    ambiente.pop(ENV_CARGA, None)   # cinto e suspensório: nunca propagar carga
    return ambiente


def executar_pytest(alvo: Alvo, destino: Path,
                    base_env: dict[str, str] | None = None) -> dict | None:
    """Roda a suíte passiva e devolve o summary.json — ou None se não saiu.

    O código de saída do pytest é IGNORADO de propósito: FAIL é dado da campanha
    (é o veredito sobre o alvo), não erro do runner. O que interessa é se o
    artefato foi produzido.
    """
    destino.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # nosec B603
        [sys.executable, "-m", "pytest", "-m", SELECAO, "-q", "-p", "no:cacheprovider"],
        cwd=RAIZ, env=env_da_execucao(alvo, destino, base_env),
        capture_output=True, text=True, timeout=1800, check=False,
    )
    caminho = destino / "summary.json"
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def informar(mensagem: str) -> None:
    """Progresso com flush explícito.

    A campanha leva dezenas de minutos e o stdout do Python é bufferizado quando
    redirecionado (`make campanha | tee`, log de cron, captura de CI). Sem o
    flush, quem acompanha vê silêncio absoluto do início ao fim e não tem como
    distinguir "rodando o alvo 2" de "travado no alvo 1".
    """
    print(mensagem, flush=True)


def rodar(campanha: Campanha, saida: Path, *,
          preflight=preflight_http, executar=executar_pytest,
          pausar=time.sleep, log=informar) -> list[ResultadoAlvo]:
    """Percorre alvo × repetição. Falha de rede num alvo não derruba a campanha.

    As dependências entram por parâmetro para que a verificação exercite o laço
    inteiro sem tocar a rede — mesma razão pela qual os checks só conhecem
    fixtures.
    """
    resultados: list[ResultadoAlvo] = []
    primeira = True
    for alvo in campanha.alvos:
        ok, motivo = preflight(alvo)
        if not ok:
            log(f"  [{alvo.host}] INACESSÍVEL ({motivo}) — segue para o próximo alvo")
            resultados.append(ResultadoAlvo(alvo, acessivel=False, motivo=motivo))
            continue

        resultado = ResultadoAlvo(alvo, motivo=motivo)
        for n in range(1, campanha.repeticoes + 1):
            if not primeira:
                # Pausa ENTRE execuções, inclusive na virada de alvo: a rede e o
                # proxy daqui são compartilhados, e execuções encavaladas
                # contaminariam a medida do alvo seguinte.
                pausar(campanha.pausa_s)
            primeira = False
            destino = saida / alvo.host / f"run{n}"
            log(f"  [{alvo.host}] execução {n}/{campanha.repeticoes} → {destino}")
            summary = executar(alvo, destino)
            if summary is None:
                log(f"  [{alvo.host}] execução {n} não produziu summary.json")
                continue
            resultado.execucoes.append(summary)
        if not resultado.execucoes:
            # Passou no preflight e ainda assim nenhuma execução rendeu artefato:
            # é inacessível na prática, e dizer isso é melhor que exibir um alvo
            # vazio como se tivesse sido medido.
            resultado.acessivel = False
            resultado.motivo = "preflight OK, mas nenhuma execução produziu summary.json"
        resultados.append(resultado)
    return resultados


# ---------------------------------------------------------------- consolidação

def resumo(amostras: list[float]) -> dict | None:
    """Mediana E pior caso. Sem amostra, None — não zero."""
    limpas = [float(a) for a in amostras if a is not None]
    if not limpas:
        return None
    return {
        "mediana": round(statistics.median(limpas), 3),
        "pior": round(max(limpas), 3),
        "n": len(limpas),
    }


def _estado(resultado: dict) -> str:
    """`estado` distingue xfail de skip; `outcome` não. Ver webqa/report.py."""
    return resultado.get("estado") or resultado.get("outcome") or "skipped"


def _dimensoes(resultado: dict) -> list[str]:
    return resultado.get("dimensions") or [resultado.get("dimension", "other")]


def _pior(a: str, b: str) -> str:
    """O mais severo dos dois estados (desconhecido perde para conhecido)."""
    ordem = {estado: i for i, estado in enumerate(SEVERIDADE)}
    return a if ordem.get(a, -1) >= ordem.get(b, -1) else b


def estados_por_teste(summary: dict) -> dict[str, str]:
    """UM desfecho por teste nesta execução, colapsado pelo pior estado.

    Necessário porque uma execução pode registrar setup, call e teardown do mesmo
    teste. Sem o colapso, um teardown quebrado apareceria como segunda amostra e
    a campanha acusaria instabilidade que não existe.
    """
    colapsado: dict[str, str] = {}
    for resultado in summary.get("results", []):
        teste = resultado["test"]
        estado = _estado(resultado)
        colapsado[teste] = _pior(colapsado.get(teste, "passed"), estado) if teste in colapsado \
            else estado
    return colapsado


def duracoes_por_teste(summary: dict) -> dict[str, float]:
    """Tempo por teste nesta execução, SOMANDO as fases.

    Setup caro é custo do teste tanto quanto o corpo — e é onde mora o tempo de
    quem levanta navegador."""
    somas: dict[str, float] = {}
    for resultado in summary.get("results", []):
        somas[resultado["test"]] = (somas.get(resultado["test"], 0.0)
                                    + float(resultado.get("duration_s", 0.0)))
    return somas


def placar(contagem: Counter) -> str:
    """"2×passed 1×failed" — o formato que a OS pede, sem média escondendo nada."""
    ordenado = sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    return " ".join(f"{n}×{estado}" for estado, n in ordenado)


def instabilidades(execucoes: list[dict]) -> list[dict]:
    """Testes cujo veredito MUDOU entre repetições do mesmo alvo.

    Inclui o teste que desapareceu numa repetição (contado como `ausente`):
    sumir da coleta é instabilidade tanto quanto trocar de veredito, e sem essa
    contagem um teste que só roda 2 de 3 vezes passaria por estável.
    """
    total = len(execucoes)
    por_teste: dict[str, Counter] = {}
    for summary in execucoes:
        for teste, estado in estados_por_teste(summary).items():
            por_teste.setdefault(teste, Counter())[estado] += 1

    achados = []
    for teste, contagem in sorted(por_teste.items()):
        vistos = sum(contagem.values())
        if vistos < total:
            contagem = Counter(contagem)
            contagem["ausente"] = total - vistos
        if len(contagem) > 1:
            achados.append({"test": teste, "placar": placar(contagem),
                            "estados": dict(contagem)})
    return achados


def por_dimensao(execucoes: list[dict]) -> dict[str, dict]:
    """Contagem por dimensão e estado, com a VARIAÇÃO entre repetições exposta.

    Guarda min e max de cada estado. Quando diferem, o consolidado imprime a
    faixa (`2–3`): a variação é o sinal, e um número único a apagaria.
    """
    bruto: dict[str, dict[str, list[int]]] = {}
    parede: dict[str, list[float]] = {}
    for summary in execucoes:
        contagem: dict[str, Counter] = {}
        somas: dict[str, float] = {}
        colapsado = estados_por_teste(summary)
        tempos = duracoes_por_teste(summary)
        dims_do_teste = {r["test"]: _dimensoes(r) for r in summary.get("results", [])}
        for teste, estado in colapsado.items():
            for dim in dims_do_teste.get(teste, ["other"]):
                contagem.setdefault(dim, Counter())[estado] += 1
                somas[dim] = somas.get(dim, 0.0) + tempos.get(teste, 0.0)
        for dim, cont in contagem.items():
            alvo_dim = bruto.setdefault(dim, {})
            for estado in ESTADOS:
                alvo_dim.setdefault(estado, []).append(cont.get(estado, 0))
        for dim, soma in somas.items():
            parede.setdefault(dim, []).append(soma)

    consolidado = {}
    for dim in sorted(bruto):
        estados = {}
        for estado in ESTADOS:
            valores = bruto[dim].get(estado) or [0]
            estados[estado] = {"min": min(valores), "max": max(valores),
                               "mediana": round(statistics.median(valores), 1)}
        consolidado[dim] = {"estados": estados, "tempo_s": resumo(parede.get(dim, []))}
    return consolidado


def mais_lentos(execucoes: list[dict], limite: int = TOP_LENTOS) -> list[dict]:
    """Top-N testes por tempo MEDIANO, com o pior caso ao lado.

    Ranquear pelo pior caso colocaria no topo o teste que travou uma vez; pela
    mediana, quem custa caro sempre. Os dois números juntos separam "lento" de
    "instável" — e as duas doenças têm tratamentos diferentes.
    """
    tempos: dict[str, list[float]] = {}
    for summary in execucoes:
        for teste, total in duracoes_por_teste(summary).items():
            tempos.setdefault(teste, []).append(total)
    ranking = []
    for teste, amostras in tempos.items():
        dados = resumo(amostras)
        if dados:
            ranking.append({"test": teste, "mediana_s": dados["mediana"],
                            "pior_s": dados["pior"], "n": dados["n"]})
    ranking.sort(key=lambda r: (-r["mediana_s"], r["test"]))
    return ranking[:limite]


def consolidar(resultados: list[ResultadoAlvo], *, gerado_em: str,
               parede_total_s: float, repeticoes: int) -> dict:
    """Função PURA: recebe o que foi observado, devolve o consolidado.

    Sem rede, sem disco, sem relógio — é o que permite verificá-la com summaries
    fabricados em tmp_path, que é onde a instabilidade 2×1 é testável de fato.
    """
    alvos = []
    for resultado in resultados:
        registro = {
            "url": resultado.alvo.url,
            "host": resultado.alvo.host,
            "papel": resultado.alvo.papel,
            "acessivel": resultado.acessivel,
            "motivo": resultado.motivo,
            "execucoes": len(resultado.execucoes),
        }
        if resultado.acessivel and resultado.execucoes:
            metricas = {}
            for chave, _rotulo in METRICAS:
                amostras = [s.get("metricas", {}).get(chave)
                            for s in resultado.execucoes
                            if s.get("metricas", {}).get(chave) is not None]
                dados = resumo(amostras)
                if dados:
                    # Amostra faltando é dito, não interpolado: métrica medida em
                    # 1 de 3 execuções não vale o mesmo que medida em 3.
                    dados["faltando"] = len(resultado.execucoes) - dados["n"]
                    metricas[chave] = dados
            registro.update({
                "metricas": metricas,
                "dimensoes": por_dimensao(resultado.execucoes),
                "instaveis": instabilidades(resultado.execucoes),
                "mais_lentos": mais_lentos(resultado.execucoes),
                "parede_por_execucao_s": resumo(
                    [float(s.get("duration_s", 0.0)) for s in resultado.execucoes]),
            })
        alvos.append(registro)

    acessiveis = [a for a in alvos if a["acessivel"]]
    return {
        "gerado_em": gerado_em,
        "repeticoes": repeticoes,
        "selecao": SELECAO,
        "parede_total_s": round(parede_total_s, 1),
        "alvos_acessiveis": len(acessiveis),
        "alvos_total": len(alvos),
        "alvos": alvos,
    }


# ---------------------------------------------------------------- markdown

def _faixa(estado: dict) -> str:
    """`2` quando estável entre repetições, `2–3` quando variou."""
    if estado["min"] == estado["max"]:
        return str(estado["min"])
    return f"{estado['min']}–{estado['max']}"


def _num(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def render_markdown(dados: dict) -> str:
    """Consolidado legível. Pior caso ao lado da mediana em toda linha."""
    L: list[str] = []
    L.append("# Campanha da suíte contra alvos reais")
    L.append("")
    L.append(f"* **Gerado em**: {dados['gerado_em']}")
    L.append(f"* **Repetições por alvo**: {dados['repeticoes']}")
    L.append(f"* **Seleção**: `pytest -m \"{dados['selecao']}\"`")
    L.append(f"* **Parede total da campanha**: {_num(dados['parede_total_s'])} s")
    L.append(f"* **Alvos medidos**: {dados['alvos_acessiveis']} de {dados['alvos_total']}")
    L.append("")
    L.append("Toda métrica aparece em **mediana e pior caso**: o pior caso é o que o "
             "usuário azarado viveu, e a mediana sozinha faz alvo intermitente parecer "
             "saudável. Veredito que muda entre repetições é marcado como **instável** "
             "e nunca agregado em média.")
    L.append("")

    inacessiveis = [a for a in dados["alvos"] if not a["acessivel"]]
    if inacessiveis:
        L.append("## Alvos inacessíveis")
        L.append("")
        L.append("Falha de rede num alvo não derruba a campanha — fica registrada.")
        L.append("")
        L.append("| Alvo | Papel | Motivo |")
        L.append("| --- | --- | --- |")
        for a in inacessiveis:
            L.append(f"| `{a['host']}` | {a['papel']} | {a['motivo']} |")
        L.append("")

    # ---- Seção 1: tempo DO ALVO
    L.append("## Tempo do alvo (o que o usuário do alvo sente)")
    L.append("")
    medidos = [a for a in dados["alvos"] if a["acessivel"] and a.get("metricas")]
    if not medidos:
        L.append("Nenhum alvo rendeu métrica nesta campanha.")
        L.append("")
    else:
        cabecalho = "| Métrica | " + " | ".join(
            f"{a['host']} (mediana / pior)" for a in medidos) + " |"
        L.append(cabecalho)
        L.append("| --- |" + " --- |" * len(medidos))
        for chave, rotulo in METRICAS:
            celulas = []
            for a in medidos:
                m = a["metricas"].get(chave)
                if not m:
                    celulas.append("não medido")
                    continue
                casas = 3 if chave == "cls" else 0
                texto = f"{_num(m['mediana'], casas)} / {_num(m['pior'], casas)}"
                if m.get("faltando"):
                    texto += f" ⚠ {m['faltando']} sem amostra"
                celulas.append(texto)
            L.append(f"| {rotulo} | " + " | ".join(celulas) + " |")
        L.append("")

    # ---- Seção 2: tempo DA SUÍTE
    L.append("## Tempo da suíte (o que custa medir)")
    L.append("")
    for a in dados["alvos"]:
        if not a["acessivel"]:
            continue
        parede = a.get("parede_por_execucao_s")
        L.append(f"### `{a['host']}` — {a['papel']}")
        L.append("")
        if parede:
            L.append(f"Parede por execução: mediana {_num(parede['mediana'])} s, "
                     f"pior {_num(parede['pior'])} s ({a['execucoes']} execuções).")
            L.append("")
        L.append("| Dimensão | passed | failed | xfail | skipped | error | "
                 "tempo somado (mediana / pior) |")
        L.append("| --- | --- | --- | --- | --- | --- | --- |")
        for dim, info in (a.get("dimensoes") or {}).items():
            e = info["estados"]
            t = info.get("tempo_s")
            tempo = f"{_num(t['mediana'])} / {_num(t['pior'])} s" if t else "—"
            L.append(f"| {dim} | {_faixa(e['passed'])} | {_faixa(e['failed'])} | "
                     f"{_faixa(e['xfail'])} | {_faixa(e['skipped'])} | {_faixa(e['error'])} "
                     f"| {tempo} |")
        L.append("")
        L.append("Faixa (`2–3`) marca variação entre repetições. `error` é falha FORA do "
                 "corpo do teste (fixture, navegador, rede) — não é veredito sobre o alvo, "
                 "é o teste não tendo acontecido, e por isso não se soma a `failed`. "
                 "O tempo é a SOMA dos testes da dimensão, não parede exclusiva: teste "
                 "multidimensional conta nas duas dimensões, e o custo de fixture de "
                 "sessão cai sobre o teste que a acionou.")
        L.append("")
        lentos = a.get("mais_lentos") or []
        if lentos:
            L.append(f"**Top-{len(lentos)} mais lentos** (ranqueado pela mediana):")
            L.append("")
            L.append("| # | Teste | Mediana | Pior caso |")
            L.append("| --- | --- | --- | --- |")
            for i, t in enumerate(lentos, 1):
                L.append(f"| {i} | `{t['test']}` | {_num(t['mediana_s'], 2)} s | "
                         f"{_num(t['pior_s'], 2)} s |")
            L.append("")

    # ---- Seção 3: instabilidade
    L.append("## Estabilidade do veredito entre repetições")
    L.append("")
    algum = False
    for a in dados["alvos"]:
        if not a["acessivel"]:
            continue
        instaveis = a.get("instaveis") or []
        L.append(f"### `{a['host']}`")
        L.append("")
        if not instaveis:
            L.append(f"Nenhum veredito divergente em {a['execucoes']} repetições.")
            L.append("")
            continue
        algum = True
        L.append("| Teste | Placar entre repetições |")
        L.append("| --- | --- |")
        for i in instaveis:
            L.append(f"| `{i['test']}` | **{i['placar']}** |")
        L.append("")
    if algum:
        L.append("Teste instável não é veredito sobre o alvo: é dívida da suíte ou "
                 "variação real do alvo, e as duas precisam ser investigadas antes de "
                 "o número ser citado em qualquer laudo.")
        L.append("")

    L.append("---")
    L.append("")
    L.append("Campanha passiva: nenhuma requisição além da navegação normal da suíte, "
             "crawl reduzido por alvo e pausa mínima entre execuções. O código de saída "
             "fala da CAMPANHA, não da conformidade dos alvos — alvo reprovado é dado, "
             "não erro de execução.")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Campanha da suíte contra alvos reais.")
    parser.add_argument("--campanha", type=Path, default=CAMPANHA_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--repeticoes", type=int, default=None,
                        help="sobrepõe o valor de campanha.yaml")
    args = parser.parse_args(argv)

    try:
        # Ordem importa: a guarda vem antes de ler qualquer coisa e,
        # principalmente, antes de tocar a rede.
        verificar_ambiente_passivo()
        campanha = carregar_campanha(args.campanha)
    except CampanhaAbortada as erro:
        print(f"ABORTADA: {erro}", file=sys.stderr)
        return 2

    if args.repeticoes:
        campanha = Campanha(campanha.alvos, max(1, args.repeticoes), campanha.pausa_s)

    informar(f"Campanha: {len(campanha.alvos)} alvos × {campanha.repeticoes} repetições, "
             f"pausa de {campanha.pausa_s:.0f}s, seleção `{SELECAO}`")
    inicio = time.time()
    resultados = rodar(campanha, args.saida)
    parede = time.time() - inicio

    dados = consolidar(resultados, gerado_em=time.strftime("%Y-%m-%d %H:%M:%S"),
                       parede_total_s=parede, repeticoes=campanha.repeticoes)
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "consolidado.json").write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.saida / "consolidado.md").write_text(render_markdown(dados), encoding="utf-8")

    informar(f"\nConsolidado em {args.saida / 'consolidado.md'} "
             f"({dados['alvos_acessiveis']}/{dados['alvos_total']} alvos medidos, "
             f"parede {parede:.0f}s)")
    if not dados["alvos_acessiveis"]:
        print("ERRO: nenhum alvo acessível — campanha sem medida.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
