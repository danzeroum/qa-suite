"""Cockpit de testes — veste o catálogo (scripts/catalogo.py) de HTML (D1k).

`report/cockpit.html` (arquivo único, offline) e `report/cockpit.json` saem da
MESMA leitura. O JSON é a fonte única; o HTML é outra veste — nenhuma contagem é
digitada no template, tudo interpola do catálogo. Espelha o protótipo de 11 telas
(docs/handoff-cockpit-dev/), com os tokens de referencia/summary.html.

Invariantes de honestidade (nenhuma tela viola):
* as duas populações — `alvo` (checks/) e `suite` (tests/) — NUNCA se somam;
* não-executado nunca vira 0 nem verde: é estado NOMEADO, célula tracejada;
* ausência de MEDIÇÃO (cobertura/mutação/complexidade, D5k) é "não instrumentada"
  nomeada, jamais 0%/barra verde;
* cor cromática é exclusiva de estado de teste;
* `comparavel=null` enquanto o carimbo (padrao_versao/hash) estiver pendente.

Arquitetura "módulo novo = função nova": um montador puro por tela,
`montar_*(catalogo, run) -> bloco`. Somente stdlib.

Uso:
    python scripts/cockpit.py --html                 # lê o repo (AST) + report/summary.json
    python scripts/cockpit.py --html --de-json X.json  # veste um catálogo pronto (dogfooding)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

# Raiz no path para `from scripts.catalogo import ...` funcionar tanto como
# script (`python scripts/cockpit.py`) quanto importado (`scripts.cockpit`, testes).
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from scripts.catalogo import RAIZ_PADRAO  # noqa: E402
from scripts.catalogo import montar_catalogo as construir_catalogo  # noqa: E402

# Tokens EXATOS de referencia/summary.html (OS-27) — nenhum tom novo.
TOKENS = {
    "fundo": "#F5F3EF", "papel": "#FFFFFF", "tinta": "#1C2228", "apagado": "#4A5560",
    "linha": "#DED9D1", "well": "#EDF2F7", "passed": "#2F6B4F", "xfail": "#8A5800",
    "failed": "#9E2222", "skipped": "#5C6670", "nao_exec": "#1E5A8A",
    "vazio": "#E7E2D9", "tracejado": "#B8B1A6",
}
# Estado de teste → (rótulo pt-BR, cor). `nao-executado` não é cromático: é vazio.
ESTADOS = {
    "passed": ("aprovado", TOKENS["passed"]),
    "failed": ("reprovado", TOKENS["failed"]),
    "xfail": ("falha esperada", TOKENS["xfail"]),
    "xpassed": ("passou inesperado", TOKENS["xfail"]),
    "skipped": ("pulado", TOKENS["skipped"]),
    "error": ("erro", TOKENS["failed"]),
    "nao-executado": ("não executado", TOKENS["nao_exec"]),
}
NIVEIS_ORDEM = ("unidade", "integracao", "sistema", "aceitacao")
NIVEL_ROTULO = {"unidade": "Unidade", "integracao": "Integração",
                "sistema": "Sistema", "aceitacao": "Aceitação"}
POP_ROTULO = {"alvo": "Alvo (checks/ — julga o site publicado)",
              "suite": "Suíte (tests/ — verifica a própria ferramenta)"}
# Blocos de MEDIÇÃO opcionais (D5k). Ausentes → estado nomeado, nunca 0/verde.
BLOCOS_D5K = (("cobertura_codigo", "Cobertura de código"),
              ("mutacao", "Score de mutação"), ("complexidade", "Complexidade ciclomática"))

# Os 4 modos, em ESCADA DE GRAVIDADE (D2k). O cockpit lê só o código: sua própria
# leitura é sempre `inventario`. A escada mostra o que EXISTE, marcando o corrente.
MODOS = (
    ("inventario", "Inventário", "lê o código; nenhuma requisição sai"),
    ("passivo", "Passivo", "GET normais contra o alvo declarado"),
    ("carga", "Carga", "rajada de requisições — exige WEBQA_LOAD_AUTHORIZED"),
    ("sondagem", "Sondagem ativa", "pede recursos não linkados — gate + escopo + posse"),
)
# Gates de REDE cujo valor no ambiente arma o alarme do selo (§7.2 da arquitetura).
# KILL é freio de emergência, não perigo — some do alarme, aparece à parte.
GATES_REDE = ("WEBQA_DISCOVERY_AUTHORIZED", "WEBQA_ACTIVE_PROBES_AUTHORIZED",
              "WEBQA_LOAD_AUTHORIZED")
GATE_KILL = "WEBQA_ACTIVE_PROBES_KILL"


def estado_do_ambiente(env: dict | None = None) -> dict:
    """Modo da leitura + gates de rede ativos, lidos do ambiente. O cockpit só faz
    inventário (AST), então o modo é sempre `inventario`; os gates de rede ATIVOS
    no ambiente armam o alarme — uma leitura de inventário nunca deveria vê-los."""
    env = env if env is not None else os.environ
    ativos = [g for g in GATES_REDE if str(env.get(g, "")).strip()]
    kill = bool(str(env.get(GATE_KILL, "")).strip())
    return {"modo": "inventario", "gates_ativos": ativos, "kill": kill}


def _e(texto) -> str:
    return html.escape(str(texto), quote=True)


def _num(v: float, casas: int = 1) -> str:
    """Número em pt-BR: vírgula decimal, sem zeros à toa."""
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer()):
        return f"{int(v):,}".replace(",", ".")
    return f"{v:.{casas}f}".replace(".", ",")


# ============================================================ montadores (telas)
def montar_mapa(catalogo: dict, run: dict) -> str:
    """Tela 1 — mapa: 1 célula = 1 caso, agrupado por população. Não-executado é
    célula tracejada (presença NOMEADA), nunca ausência."""
    partes = ['<section id="mapa" class="tela"><h1>Todos os testes que existem no '
              'código — executados ou não.</h1>',
              '<p class="moldura">Uma célula, um caso. A cor só aparece quando houve '
              'veredito; o tracejado é o que ninguém rodou ainda — e continua à vista.</p>']
    por_pop: dict[str, list[dict]] = {"alvo": [], "suite": []}
    for t in catalogo["testes"]:
        por_pop[t["populacao"]].append(t)
    for pop in ("alvo", "suite"):
        testes = por_pop[pop]
        casos = sum(t["casos"] for t in testes)
        partes.append(f'<h2>{_e(POP_ROTULO[pop])}</h2>')
        partes.append(f'<p class="apagado">{_num(len(testes))} testes · {_num(casos)} casos</p>')
        partes.append('<div class="mapa" role="group" aria-label="mapa de casos">')
        for t in testes:
            rotulo, cor = ESTADOS.get(t["estado"], ESTADOS["nao-executado"])
            classe = "cel" if t["estado"] != "nao-executado" else "cel vazia"
            estilo = f'style="background:{cor}"' if t["estado"] != "nao-executado" else ""
            for _ in range(t["casos"]):
                partes.append(
                    f'<span class="{classe}" {estilo} tabindex="0" '
                    f'aria-label="{_e(t["nodeid"])} — {_e(rotulo)}"></span>')
        partes.append("</div>")
    partes.append('<div aria-live="polite" class="viva" id="mapa-viva"></div>')
    partes.append("</section>")
    return "".join(partes)


def montar_populacoes(catalogo: dict, run: dict) -> str:
    """Tela 1 (bloco) — as duas populações, lado a lado, NUNCA somadas."""
    pops = catalogo["agregados"]["populacoes"]
    linhas = "".join(
        f'<tr><td>{_e(POP_ROTULO[p])}</td><td class="num">{_num(pops.get(p, 0))}</td></tr>'
        for p in ("alvo", "suite"))
    return ('<section id="populacoes" class="tela"><h1>Duas populações que não se '
            'somam.</h1><p class="moldura">Uma julga o site; a outra verifica a '
            'ferramenta. Um número que as some não significa nada.</p>'
            f'<table class="dados"><thead><tr><th>População</th><th class="num">Testes'
            f'</th></tr></thead><tbody>{linhas}</tbody></table>'
            '<p class="apagado">Total combinado deliberadamente ausente: as populações '
            'medem coisas diferentes.</p></section>')


def _grade_celulas(itens: list[tuple[str, str]]) -> str:
    """Grade de células (1=1 teste) rotuladas por estado — usada em Níveis/Dimensões."""
    cels = []
    for estado, nodeid in itens:
        rotulo, cor = ESTADOS.get(estado, ESTADOS["nao-executado"])
        rot = f'aria-label="{_e(nodeid)} — {_e(rotulo)}"'
        if estado == "nao-executado":
            cels.append(f'<span class="cel vazia" tabindex="0" {rot}></span>')
        else:
            cels.append(f'<span class="cel" style="background:{cor}" tabindex="0" {rot}></span>')
    return f'<div class="mapa">{"".join(cels)}</div>'


def montar_niveis(catalogo: dict, run: dict) -> str:
    """Tela 1 (bloco) — níveis como grade de células (1=1 teste)."""
    niveis = catalogo["agregados"]["niveis"]
    por_nivel: dict[str, list[dict]] = {}
    for t in catalogo["testes"]:
        por_nivel.setdefault(t["nivel"], []).append(t)
    blocos = []
    for nv in NIVEIS_ORDEM:
        if nv not in niveis:
            continue
        itens = [(t["estado"], t["nodeid"]) for t in por_nivel.get(nv, [])]
        blocos.append(f'<h3>{_e(NIVEL_ROTULO[nv])} <span class="apagado">'
                      f'{_num(niveis[nv])}</span></h3>{_grade_celulas(itens)}')
    return ('<section id="niveis" class="tela"><h1>Por nível, de unidade a '
            f'aceitação.</h1>{"".join(blocos)}</section>')


def montar_dimensoes(catalogo: dict, run: dict) -> str:
    """Tela 1 (bloco) — dimensões DERIVADAS dos markers presentes. Marker novo no
    pytest.ini vira linha nova aqui sem tocar o gerador; dimensão sem teste some."""
    dims = catalogo["agregados"]["por_dimensao"]
    if not dims:
        return ('<section id="dimensoes" class="tela"><h1>Dimensões.</h1>'
                '<p class="vazio-nota">Nenhuma dimensão marcada no código.</p></section>')
    linhas = []
    for dim in sorted(dims):
        bloco = dims[dim]
        exec_ = bloco.get("total", 0) - bloco.get("nao-executado", 0)
        linhas.append(
            f'<tr><td>{_e(dim)}</td><td class="num">{_num(bloco.get("total", 0))}</td>'
            f'<td class="num">{_num(exec_)}</td>'
            f'<td class="num nao-exec">{_num(bloco.get("nao-executado", 0))}</td></tr>')
    return ('<section id="dimensoes" class="tela"><h1>Por dimensão de qualidade.</h1>'
            '<table class="dados"><thead><tr><th>Dimensão</th><th class="num">Testes</th>'
            '<th class="num">Executados</th><th class="num">Não executados</th></tr>'
            f'</thead><tbody>{"".join(linhas)}</tbody></table></section>')


def montar_execucao(catalogo: dict, run: dict) -> str:
    """Tela 2 — execução & descritiva: tri-números por população, com outliers por
    Tukey. Sem execução, diz "sem execução" — não zeros."""
    ag = catalogo["agregados"]
    blocos = []
    for pop, chave in (("alvo", "duracao_alvo"), ("suite", "duracao_suite")):
        d = ag.get(chave) or {}
        blocos.append(f'<h2>{_e(POP_ROTULO[pop])}</h2>')
        if not d:
            blocos.append('<p class="vazio-nota">Sem execução: nenhuma duração a '
                          'descrever. (Rode a suíte para preencher.)</p>')
            continue
        blocos.append(
            '<dl class="tri">'
            f'<div><dt>mediana</dt><dd>{_num(d["mediana"], 3)} s</dd></div>'
            f'<div><dt>média</dt><dd>{_num(d["media"], 3)} s</dd></div>'
            f'<div><dt>p95</dt><dd>{_num(d["p95"], 3)} s</dd></div>'
            f'<div><dt>desvio</dt><dd>{_num(d["desvio"], 3)} s</dd></div>'
            f'<div><dt>n</dt><dd>{_num(d["n"])}</dd></div>'
            f'<div><dt>total</dt><dd>{_num(d["total_s"], 3)} s</dd></div>'
            f'<div><dt>outliers (Tukey)</dt><dd>{_num(d["outliers"])} '
            f'<span class="apagado">acima de {_num(d["limite_outlier"], 3)} s</span></dd></div>'
            '</dl>')
    rec = catalogo["reconciliacao"]
    orfaos = rec.get("orfaos") or []
    nota_orfaos = (f'<p class="atencao">{_num(len(orfaos))} órfão(s): resultado de '
                   'teste que não existe mais no código.</p>' if orfaos else "")
    return ('<section id="execucao" class="tela"><h1>O catálogo é a população; o run '
            f'é a amostra.</h1>{"".join(blocos)}'
            f'<p class="apagado">Reconciliação: {_num(rec["executados"])} executados, '
            f'{_num(rec["nunca_vistos"])} nunca vistos.</p>{nota_orfaos}</section>')


def montar_catalogo(catalogo: dict, run: dict) -> str:
    """Tela 4 — catálogo navegável (íntegro sem JS: mostra tudo; JS só filtra)."""
    linhas = []
    for t in catalogo["testes"]:
        rotulo, _cor = ESTADOS.get(t["estado"], ESTADOS["nao-executado"])
        dims = ", ".join(t["dimensoes"]) or "—"
        contrato = _e(t["garante"]) if t["garante"] else '<span class="apagado">sem contrato</span>'
        linhas.append(
            f'<tr data-pop="{_e(t["populacao"])}" data-estado="{_e(t["estado"])}">'
            f'<td class="mono">{_e(t["nodeid"])}</td><td>{_e(dims)}</td>'
            f'<td>{_e(rotulo)}</td><td class="contrato">{contrato}</td></tr>')
    return ('<section id="catalogo" class="tela"><h1>O catálogo inteiro, teste a '
            'teste.</h1><p class="moldura">Sem JavaScript, a tabela mostra tudo. Com '
            'ele, os chips filtram sem recarregar.</p>'
            '<table class="dados catalogo"><thead><tr><th>nodeid</th><th>dimensões</th>'
            '<th>último veredito</th><th>contrato</th></tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></section>')


def montar_leitura(catalogo: dict, run: dict) -> str:
    """Tela 5 — modo leitura em graus: 1 arquivos → 2 contratos → 3 completo. O
    grau 2 DECLARA quantos testes não têm contrato e por isso não aparecem nele."""
    por_arq: dict[str, list[dict]] = {}
    for t in catalogo["testes"]:
        por_arq.setdefault(t["arquivo"], []).append(t)
    sem_contrato = catalogo["agregados"]["sem_contrato"]
    grau1 = "".join(f'<li class="mono">{_e(a)} <span class="apagado">'
                    f'({_num(len(por_arq[a]))})</span></li>' for a in sorted(por_arq))
    linhas_contrato = []
    for a in sorted(por_arq):
        for t in por_arq[a]:
            if t["garante"]:
                linhas_contrato.append(f'<li><span class="mono">{_e(t["funcao"])}</span>'
                                       f' — <span class="contrato">{_e(t["garante"])}</span></li>')
    return ('<section id="leitura" class="tela"><h1>Ler a suíte inteira, em graus: '
            'arquivos, contratos, tudo.</h1>'
            f'<details open><summary>Grau 1 — arquivos ({_num(len(por_arq))})</summary>'
            f'<ul class="graus">{grau1}</ul></details>'
            f'<details><summary>Grau 2 — contratos escritos</summary>'
            f'<p class="vazio-nota">{_num(sem_contrato)} teste(s) sem contrato não '
            f'aparecem neste grau — veja-os no grau 3.</p>'
            f'<ul class="graus">{"".join(linhas_contrato)}</ul></details>'
            '<details><summary>Grau 3 — completo</summary>'
            '<p class="apagado">Todos os testes, com e sem contrato, na tela Catálogo.</p>'
            '</details></section>')


def _selo_de_modo(modo_atual: str, gates: list[str], kill: bool) -> str:
    """Selo dos 4 modos em escada de gravidade (D2k). O alarme vermelho SÓ veste
    quando há gate de REDE ativo — cor cromática nunca decora, sempre significa."""
    tem_alarme = bool(gates)
    degraus = []
    for chave, rotulo, desc in MODOS:
        classe = "degrau atual" if chave == modo_atual else "degrau"
        marca = " ◀ esta leitura" if chave == modo_atual else ""
        degraus.append(f'<li class="{classe}"><b>{_e(rotulo)}</b>{_e(marca)}'
                       f'<span class="apagado"> — {_e(desc)}</span></li>')
    if tem_alarme:
        gate_txt = ", ".join(gates)
        alarme = (f'<p class="alarme">Gate de rede ATIVO no ambiente: {_e(gate_txt)}. '
                  'Uma leitura de inventário não deveria vê-lo — o ambiente do gerador '
                  'deveria estar limpo.</p>')
    else:
        alarme = '<p class="sereno">Nenhum gate de rede no ambiente — como deve ser.</p>'
    kill_txt = ('<p class="apagado">Freio de emergência (kill-switch) armado.</p>'
                if kill else "")
    return (f'<ol class="escada">{"".join(degraus)}</ol>{alarme}{kill_txt}')


def _incomparabilidade(padrao_versao, hash_, segundo_projeto) -> str:
    """D4k: quando falta eixo, NOMEIA qual — nunca célula vazia, nunca 'comparável'
    presumido. `comparavel` só é verdadeiro com todos os eixos presentes."""
    if padrao_versao is not None and hash_ is not None and segundo_projeto:
        return (f'<p class="ok">Comparável: régua declarada (versão '
                f'{_e(padrao_versao)}) e há um 2º projeto.</p>')
    faltas = []
    if padrao_versao is None:
        faltas.append("versão do padrão (pendente até a frente E — pacote versionado)")
    if hash_ is None:
        faltas.append("hash da lista curada (o run carimba via D6k; sem run, ausente)")
    if not segundo_projeto:
        faltas.append("um 2º projeto para comparar (leitura única)")
    itens = "".join(f"<li>{_e(f)}</li>" for f in faltas)
    return ('<div class="vazio-nota"><b>Incomparável</b> — comparável=null. Falta, '
            f'nomeadamente:<ul>{itens}</ul>Nenhuma comparação entre projetos é emitida.</div>')


def montar_regua(catalogo: dict, run: dict) -> str:
    """Tela 6 — a régua & modo: selo dos 4 modos (escada de gravidade) + gates ao
    vivo + carimbo (commit/modo vivos; versão/hash do padrão pendentes) +
    comparabilidade. Sem carimbo completo, o estado dominante é INCOMPARÁVEL, com o
    motivo NOMEADO (D2k+D4k)."""
    proc = catalogo["procedencia"]
    carimbo = run.get("carimbo") or {}
    padrao_versao = carimbo.get("padrao_versao")
    hash_ = carimbo.get("caminhos_sensiveis_hash")
    gates = run.get("gates_ativos", [])
    modo = run.get("modo", "inventario")

    def campo(rot, val):
        v = _e(val) if val else '<span class="pendente">pendente</span>'
        return f'<div><dt>{_e(rot)}</dt><dd>{v}</dd></div>'

    selo = _selo_de_modo(modo, gates, run.get("kill", False))
    comp = _incomparabilidade(padrao_versao, hash_, run.get("segundo_projeto"))
    return ('<section id="regua" class="tela"><h1>Um número só é comparável se a régua '
            'estiver declarada.</h1>'
            f'<h2>Modo desta leitura</h2>{selo}'
            f'<h2>Carimbo</h2><dl class="tri">{campo("commit", proc.get("commit"))}'
            f'{campo("ramo", proc.get("ramo"))}'
            f'{campo("versão do padrão", padrao_versao)}'
            f'{campo("hash da lista curada", hash_)}</dl>'
            f'<h2>Comparabilidade</h2>{comp}</section>')


def _bloco_ausente(rotulo: str) -> str:
    """Estado NOMEADO de medição ausente — nunca 0%/barra verde (D5k)."""
    return (f'<div class="medicao ausente"><h3>{_e(rotulo)}</h3>'
            '<p class="vazio-nota">não instrumentada — sem medição nesta leitura. '
            'Ausência de medição não é zero por cento. (Rode a ferramenta e emita '
            '<span class="mono">report/medicoes.json</span>.)</p></div>')


def _classe_score(v: float) -> str:
    return "ruim" if isinstance(v, int | float) and v < 70 else "ok"


def _bloco_cobertura(dados: dict) -> str:
    """Cobertura de código por banda + o viés (o gate roda só a população
    verification; caminhos de checks/ aparecem descobertos)."""
    total = dados.get("total")
    banda = f'<p class="{_classe_score(total)}">total {_num(total, 1)}%</p>' if total is not None else ""
    vies = dados.get("vies")
    nota = f'<p class="apagado">Viés: {_e(vies)}</p>' if vies else ""
    piores = sorted((dados.get("por_arquivo") or {}).items(), key=lambda kv: kv[1])[:5]
    linhas = "".join(f'<tr><td class="mono">{_e(a)}</td>'
                     f'<td class="num {_classe_score(p)}">{_num(p, 1)}%</td></tr>'
                     for a, p in piores)
    tabela = (f'<table class="dados"><thead><tr><th>arquivo (menor cobertura)</th>'
              f'<th class="num">%</th></tr></thead><tbody>{linhas}</tbody></table>'
              if linhas else "")
    return f'<div class="medicao"><h3>Cobertura de código</h3>{banda}{nota}{tabela}</div>'


def _bloco_mutacao(dados: dict) -> str:
    """Score de mutação por módulo — sobreviventes explícitos; score<70 em vermelho."""
    linhas = []
    for mod, bloco in sorted((dados.get("por_modulo") or {}).items()):
        sc = bloco.get("score")
        sob = bloco.get("sobreviventes", 0)
        linhas.append(f'<tr><td class="mono">{_e(mod)}</td>'
                      f'<td class="num {_classe_score(sc)}">{_num(sc, 1)}%</td>'
                      f'<td class="num">{_num(sob)}</td></tr>')
    tabela = (f'<table class="dados"><thead><tr><th>módulo</th><th class="num">score</th>'
              f'<th class="num">sobreviventes</th></tr></thead>'
              f'<tbody>{"".join(linhas)}</tbody></table>' if linhas else "")
    return f'<div class="medicao"><h3>Score de mutação</h3>{tabela}</div>'


def _bloco_complexidade(dados: dict) -> str:
    """Complexidade ciclomática: a cauda (funções acima do teto) + a decisão do
    limiar 8 (a 10 nenhuma função de webqa/ é pega — o gate não vigiaria o motor)."""
    teto = dados.get("teto", 8)
    cauda = dados.get("cauda") or []
    linhas = "".join(
        f'<tr><td class="mono">{_e(c.get("arquivo", ""))}::{_e(c.get("func", ""))}</td>'
        f'<td class="num {"ruim" if c.get("cc", 0) > teto else "ok"}">{_num(c.get("cc", 0))}</td></tr>'
        for c in cauda)
    if linhas:
        corpo = (f'<p class="apagado">Teto {_num(teto)} — a 10, nenhuma função de '
                 'webqa/ seria pega, e o gate não vigiaria o motor.</p>'
                 '<table class="dados"><thead><tr><th>função</th><th class="num">CC</th>'
                 f'</tr></thead><tbody>{linhas}</tbody></table>')
    else:
        corpo = (f'<p class="ok">Nenhuma função acima do teto {_num(teto)} — cauda '
                 'vazia.</p>')
    return f'<div class="medicao"><h3>Complexidade ciclomática</h3>{corpo}</div>'


_RENDER_MEDICAO = {"cobertura_codigo": _bloco_cobertura,
                   "mutacao": _bloco_mutacao, "complexidade": _bloco_complexidade}


def montar_motor(catalogo: dict, run: dict) -> str:
    """Tela 3 — o motor & maturidade (D5k). Topo: o firewall entre as duas
    'coberturas'. Cada bloco: rico quando medido, "não instrumentada" quando não —
    ausência NUNCA vira 0/verde."""
    medicoes = run.get("medicoes") or {}
    blocos = []
    for chave, rotulo in BLOCOS_D5K:
        dados = medicoes.get(chave)
        blocos.append(_RENDER_MEDICAO[chave](dados) if dados else _bloco_ausente(rotulo))
    return ('<section id="motor" class="tela"><h1>Quão forte é a régua — cobertura, '
            'mutação, complexidade e maturidade.</h1>'
            '<p class="firewall">Cobertura de <b>código</b> (quais linhas uma execução '
            'atinge) ≠ cobertura de <b>execução</b> (quantos testes rodaram). Nomes '
            f'parecidos, métricas diferentes — nunca somadas.</p>{"".join(blocos)}</section>')


def montar_entrega(catalogo: dict, run: dict) -> str:
    """Tela 7 — entrega & saúde. Gestão: framing navegável (o plano versionado é a
    fonte; aqui a tela existe e aponta para ele)."""
    return ('<section id="entrega" class="tela"><h1>O que está quebrado, em que ordem '
            'se conserta, o que se vigia.</h1><p class="moldura">Defeitos abertos com '
            'prova, sequência de PRs por dependência (selo CODEOWNERS onde há), frentes '
            '(E = prospectivo) e riscos vivem no plano versionado '
            '(<span class="mono">docs/PLANO-DESENVOLVIMENTO-consolidado.md</span>). Esta '
            'tela existe para que a gestão não seja um documento solto.</p></section>')


def montar_governanca(catalogo: dict, run: dict) -> str:
    """Tela 8 — governança & fronteira. Gestão: a régua da arquitetura."""
    return ('<section id="governanca" class="tela"><h1>Uma trava que o vigiado desliga '
            'em silêncio não é uma trava.</h1><p class="moldura">Dois trabalhos (A '
            'audita o alvo; B vigia os testes), a fronteira padrão × projeto (lista '
            'curada imutável pelo projeto), políticas executáveis vs. markdown, e o '
            'ambiente do agente sem gates de rede. Detalhe em '
            '<span class="mono">docs/ARQUITETURA-suite-como-padrao-em-harness.md</span>.'
            '</p></section>')


def montar_laudo(catalogo: dict, run: dict) -> str:
    """Tela 10 — laudo em prosa serif derivada + <pre> == o --json. Sem run, diz
    "não há veredito a relatar" (nunca inventa aprovação)."""
    rec = catalogo["reconciliacao"]
    ag = catalogo["agregados"]
    p = _procedencia_partes(catalogo, run)
    # Procedência ABRE o laudo (D3k): a régua antes de qualquer número, para que
    # nenhuma frase seja lida fora dela.
    regua = (f'<p class="serif">Régua desta leitura: '
             f'<span class="mono">{_e(p["repo"])}@{_e(p["commit"])}</span>, ramo '
             f'{_e(p["ramo"])}, modo {_e(p["modo"])}. Todo número abaixo vale sob esta '
             'régua, e não fora dela.</p>')
    if rec["executados"] == 0:
        prosa = regua + ('<p class="serif">Não há veredito a relatar: nenhum teste foi '
                         'executado nesta leitura. O catálogo lista '
                         f'{_num(len(catalogo["testes"]))} testes à espera de um run.</p>')
    else:
        prosa = regua + (f'<p class="serif">Esta leitura reconciliou '
                         f'{_num(rec["executados"])} execuções contra '
                         f'{_num(len(catalogo["testes"]))} testes catalogados; '
                         f'{_num(rec["nunca_vistos"])} nunca foram vistos por um run.</p>')
    # Compacto e escapando só &/</>  (dentro de <pre> aspas são literais): o <pre>
    # é parse-igual ao --json (aceite: "byte-comparável após parse"), e indentar +
    # escapar aspas multiplicaria o tamanho num catálogo cheio de strings.
    bruto = html.escape(json.dumps(catalogo, ensure_ascii=False, separators=(",", ":")),
                        quote=False)
    return ('<section id="laudo" class="tela"><h1>O que foi feito, o que não foi, e '
            f'onde está escrito.</h1>{prosa}'
            f'<p class="apagado">{_num(ag["casos"])} casos · {_num(ag["condicionais"])} '
            f'vereditos condicionais · {_num(ag["gherkin"])} cenário(s) Gherkin.</p>'
            f'<details><summary>O catálogo bruto (idêntico ao --json)</summary>'
            f'<pre class="json">{bruto}</pre></details></section>')


def montar_diff(catalogo: dict, run: dict) -> str:
    """Tela 11 — entre leituras: novos/removidos/vereditos que viraram. Uma leitura
    só → vazio honesto (não há base para comparar)."""
    base = run.get("base")
    if not base:
        return ('<section id="diff" class="tela"><h1>Aprovar é comparar: esta leitura '
                'contra a anterior.</h1><p class="vazio-nota">Uma leitura só: não há '
                'base para comparar. O diff aparece a partir da segunda leitura.</p>'
                '</section>')
    return ('<section id="diff" class="tela"><h1>Aprovar é comparar: esta leitura '
            'contra a anterior.</h1><p class="apagado">Comparação disponível.</p></section>')


# ============================================================ shell / montagem
_MONTADORES = (
    ("O todo", (montar_mapa, montar_populacoes, montar_niveis, montar_dimensoes)),
    ("O instrumento", (montar_execucao, montar_motor)),
    ("As partes", (montar_catalogo, montar_leitura)),
    ("Sob que régua", (montar_regua,)),
    ("Gestão da suíte", (montar_entrega, montar_governanca)),
    ("Para quem aprova", (montar_laudo, montar_diff)),
)


def _css() -> str:
    t = TOKENS
    return f"""
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:{t['fundo']}; color:{t['tinta']};
      font:400 15px/1.55 ui-sans-serif,system-ui,sans-serif; }}
    .layout {{ display:flex; align-items:flex-start; }}
    nav.trilho {{ position:sticky; top:0; width:15rem; flex:0 0 15rem; padding:1.5rem 1rem;
      height:100vh; overflow:auto; border-right:1px solid {t['linha']}; font-size:13.5px; }}
    nav.trilho h2 {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em;
      color:{t['apagado']}; margin:1.2rem 0 .4rem; }}
    nav.trilho a {{ display:block; color:{t['tinta']}; text-decoration:none; padding:.2rem 0; }}
    nav.trilho a:hover {{ text-decoration:underline; }}
    main {{ flex:1; padding:2rem 2.5rem; max-width:70rem; }}
    .tela {{ padding:1.5rem 0; border-bottom:1px solid {t['linha']}; scroll-margin-top:1rem; }}
    h1 {{ font:400 27px/1.3 ui-sans-serif,system-ui,sans-serif; letter-spacing:-.015em;
      margin:0 0 1rem; max-width:40ch; text-wrap:pretty; }}
    h2 {{ font-size:19px; font-weight:600; margin:1.4rem 0 .6rem; }}
    h3 {{ font-size:15px; font-weight:600; margin:1rem 0 .4rem; }}
    .moldura {{ max-width:60ch; color:{t['apagado']}; }}
    .apagado {{ color:{t['apagado']}; font-size:13.5px; }}
    .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
    .contrato {{ font-family:Charter,Georgia,serif; }}
    .serif {{ font-family:Charter,Georgia,serif; font-size:15px; max-width:62ch; }}
    .mapa {{ display:flex; flex-wrap:wrap; gap:2px; margin:.5rem 0 1rem; }}
    .cel {{ width:11px; height:11px; border-radius:2px; background:{t['skipped']}; }}
    .cel.vazia {{ background:{t['vazio']};
      border:1px dashed {t['tracejado']}; width:11px; height:11px; }}
    .cel:focus {{ outline:2px solid {t['xfail']}; outline-offset:1px; }}
    table.dados {{ border-collapse:collapse; width:100%; margin:.5rem 0 1rem; font-size:13.5px; }}
    table.dados th, table.dados td {{ text-align:left; padding:.35rem .6rem;
      border-bottom:1px solid {t['linha']}; }}
    table.dados th {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em;
      color:{t['apagado']}; font-weight:600; }}
    .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    .nao-exec {{ color:{t['nao_exec']}; }}
    dl.tri {{ display:flex; flex-wrap:wrap; gap:1.2rem 2rem; margin:.5rem 0 1rem; }}
    dl.tri dt {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:{t['apagado']}; }}
    dl.tri dd {{ margin:0; font-size:27px; font-weight:300; font-variant-numeric:tabular-nums; }}
    .vazio-nota {{ background:{t['well']}; border-left:3px solid {t['nao_exec']};
      padding:.6rem .9rem; color:{t['tinta']}; max-width:62ch; font-size:13.5px; }}
    .firewall {{ background:{t['well']}; padding:.7rem 1rem; border-radius:4px; max-width:64ch; }}
    .medicao {{ border:1px solid {t['linha']}; border-radius:4px; padding:.8rem 1rem; margin:.6rem 0; }}
    .medicao.ausente {{ border-style:dashed; border-color:{t['tracejado']}; }}
    .ok {{ color:{t['passed']}; }} .ruim {{ color:{t['failed']}; }} .atencao {{ color:{t['xfail']}; }}
    .pendente {{ color:{t['apagado']}; font-style:italic; }}
    ol.escada {{ list-style:none; padding:0; margin:.5rem 0; max-width:64ch; }}
    ol.escada .degrau {{ padding:.35rem .7rem; border-left:3px solid {t['linha']};
      margin:.15rem 0; color:{t['apagado']}; }}
    ol.escada .degrau.atual {{ border-left-color:{t['nao_exec']}; background:{t['well']};
      color:{t['tinta']}; font-weight:600; }}
    .sereno {{ color:{t['passed']}; }}
    .alarme {{ background:{t['well']}; border-left:4px solid {t['failed']};
      color:{t['failed']}; padding:.6rem .9rem; max-width:62ch; font-weight:600; }}
    details {{ margin:.5rem 0; }} summary {{ cursor:pointer; font-weight:600; }}
    ul.graus {{ columns:2; font-size:13px; }} ul.graus li {{ break-inside:avoid; }}
    pre.json {{ background:{t['papel']}; border:1px solid {t['linha']}; padding:1rem;
      overflow:auto; max-height:32rem; font-size:11px; }}
    .aviso-sem-run {{ background:{t['well']}; border-left:3px solid {t['nao_exec']};
      padding:.5rem .8rem; margin-bottom:1rem; font-size:13.5px; }}
    header.espinha {{ position:sticky; top:0; z-index:2; background:{t['papel']};
      border-bottom:1px solid {t['linha']}; padding:.5rem .9rem; font-size:12px;
      color:{t['apagado']}; margin:-2rem -2.5rem 1rem; }}
    header.espinha.alarme-espinha {{ border-bottom:2px solid {t['failed']};
      color:{t['failed']}; }}
    @media print {{
      nav.trilho {{ display:none; }} main {{ max-width:none; }}
      .tela {{ break-inside:avoid; }} .cel {{ border:1px solid {t['tinta']}; }}
      .cel.vazia {{ background:transparent; }} pre.json {{ max-height:none; }}
    }}
    """


def _trilho(catalogo: dict, run: dict) -> str:
    aviso = ""
    if catalogo["reconciliacao"]["executados"] == 0:
        aviso = ('<div class="aviso-sem-run">Sem execução: todos os testes estão como '
                 'não-executado. Os vereditos aparecem após um run.</div>')
    secoes = []
    for titulo, montadores in _MONTADORES:
        links = "".join(
            f'<a href="#{m.__name__.replace("montar_", "")}">{_e(_TITULOS[m.__name__])}</a>'
            for m in montadores)
        secoes.append(f'<h2>{_e(titulo)}</h2>{links}')
    return f'<nav class="trilho">{aviso}{"".join(secoes)}</nav>'


_TITULOS = {
    "montar_mapa": "Visão geral", "montar_populacoes": "Duas populações",
    "montar_niveis": "Níveis", "montar_dimensoes": "Dimensões",
    "montar_execucao": "Execução & descritiva", "montar_motor": "O motor & maturidade",
    "montar_catalogo": "Catálogo", "montar_leitura": "Modo leitura",
    "montar_regua": "A régua · modo", "montar_entrega": "Entrega & saúde",
    "montar_governanca": "Governança & fronteira", "montar_laudo": "Laudo",
    "montar_diff": "Entre leituras",
}


def _procedencia_partes(catalogo: dict, run: dict) -> dict:
    """Os campos da régua desta leitura, normalizados (D3k). Fonte única para a
    espinha e para o laudo — nenhum número é citado sem eles."""
    proc = catalogo.get("procedencia") or {}
    return {
        "repo": proc.get("repositorio") or "(repo local)",
        "commit": proc.get("commit") or "sem-commit",
        "ramo": proc.get("ramo") or "?",
        "modo": run.get("modo", "inventario"),
        "gates": run.get("gates_ativos") or [],
    }


def _espinha(catalogo: dict, run: dict) -> str:
    """Espinha de procedência (D3k): repo@commit · ramo · modo · gates, fixada no
    topo e presente em TODA tela. A régua deixa de ser linha de cabeçalho de uma
    tela e vira campo estrutural que acompanha qualquer agregado — nenhum número
    aparece sem dizer sob que régua foi medido."""
    p = _procedencia_partes(catalogo, run)
    gate_txt = ("⚠ gates: " + ", ".join(p["gates"])) if p["gates"] else "sem gate de rede"
    classe = "espinha alarme-espinha" if p["gates"] else "espinha"
    return (f'<header class="{classe}" role="contentinfo">'
            f'<span class="mono">{_e(p["repo"])}@{_e(p["commit"])}</span> · '
            f'ramo {_e(p["ramo"])} · modo {_e(p["modo"])} · {_e(gate_txt)}</header>')


def render_html(catalogo: dict, run: dict | None = None) -> str:
    """Documento único, offline, com as 11 telas. `run` traz execução/carimbo/D5k
    quando existem; ausência é sempre estado nomeado, nunca zero. A espinha de
    procedência (D3k) fica fixa no topo, sobre todas as telas."""
    run = run or {}
    corpo = "".join(m(catalogo, run) for _sec, ms in _MONTADORES for m in ms)
    return ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Cockpit de testes — webqa-suite</title>"
            f"<style>{_css()}</style></head><body><div class=\"layout\">"
            f"{_trilho(catalogo, run)}<main>{_espinha(catalogo, run)}{corpo}</main>"
            "</div></body></html>")


def _medicoes_do_repo(raiz: Path) -> dict:
    """Blocos de medição D5k de `report/medicoes.json`, quando as ferramentas
    (--cov, ruff C901, scripts/mutar.py) o emitiram. Ausência é o caso normal:
    o cockpit só LÊ a medição, não a produz — e ausência vira estado nomeado."""
    caminho = raiz / "report" / "medicoes.json"
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _run_do_repo(raiz: Path) -> dict:
    """Dados fora do catálogo: modo/gates do ambiente (D2k), medição D5k, e
    execução/carimbo (D3k/D6k). Ausência é o caso normal, sempre nomeada."""
    run = dict(estado_do_ambiente())
    medicoes = _medicoes_do_repo(raiz)
    if medicoes:
        run["medicoes"] = medicoes
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=RAIZ_PADRAO)
    parser.add_argument("--html", action="store_true", help="gera report/cockpit.html + .json")
    parser.add_argument("--de-json", type=Path, default=None,
                        help="veste um catálogo pronto (dogfooding) em vez de ler o repo")
    parser.add_argument("--saida", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.de_json is not None:
        catalogo = json.loads(args.de_json.read_text(encoding="utf-8"))
    else:
        catalogo = construir_catalogo(args.raiz)
    run = _run_do_repo(args.raiz)

    destino = args.saida or (args.raiz / "report" / "cockpit.html")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(render_html(catalogo, run), encoding="utf-8")
    (destino.with_suffix(".json")).write_text(
        json.dumps(catalogo, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cockpit: {destino} ({_tamanho(destino)}) · {destino.with_suffix('.json')}")
    return 0


def _tamanho(caminho: Path) -> str:
    kb = caminho.stat().st_size / 1024
    return f"{kb:.0f} KB"


if __name__ == "__main__":
    raise SystemExit(main())
