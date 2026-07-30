"""Renderização do summary.html conforme o design liberado pelo gate (OS-14).

Separado de `report.py` de propósito: aqui não há nada de pytest, então a
montagem do HTML é testável por unidade — escape, contagens, numeração A1…An e
as quatro variantes de estado, sem subir navegador nem rodar sessão.

Duas camadas que NÃO se confundem:

* **sanitização** (`webqa/sanitize.py`) tira PII do conteúdo — é sobre o titular;
* **escape** (`html.escape`, aqui) impede que `<`, `>`, `&` e aspas sejam
  interpretados como marcação — é sobre a integridade do documento.

Todo dado interpolado passa pelas duas. `detail` já chega sanitizado; o escape é
a segunda camada, e a ordem importa: escapa primeiro, destaca lei depois, porque
o destaque INSERE marcação de propósito.
"""
from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path

from webqa.report_style import ESTILO_CANONICO, FAVICON, ICONES, MARCA
from webqa.trackers import is_tracker

RAIZ = Path(__file__).resolve().parent.parent

# Rótulos textuais que acompanham cada forma — o estado nunca depende só de cor.
ROTULOS = {"failed": "achado", "xfail": "alerta", "passed": "passou", "skipped": "pulado"}
PLURAIS = {"failed": "achados", "xfail": "alertas", "passed": "passaram", "skipped": "pulados"}

# Cópia do contrato visual (referencia/summary.html): não sai de DIMENSION_NOTES,
# é texto do design — e existe para que nenhum elemento sugira certificação.
SEM_SELO = "Nenhum elemento deste relatório constitui selo, certificação ou aprovação."
# Legenda: cada estado com FORMA + rótulo + o que significa. Texto corrido não
# ensina a ler o documento; a legenda é parte do contrato de acessibilidade.
LEGENDA = {
    "failed": "= failed · prova de não conformidade",
    "xfail": "= xfail · informativo, sem obrigação legal direta",
    "passed": "= passed · conforme no observável",
    "skipped": "= skipped · não aplicável, motivo registrado",
}

# Subtítulos de seção: copy do contrato visual (.sec-sub).
SUBTITULOS = {
    "panorama": "passar é o esperado; o conteúdo deste relatório são os achados",
    "achados": "cite-os por número em tickets e planos de ação",
    "alertas": "sinais de maturidade ausentes, sem obrigação legal direta",
    "terceiros": "quem recebeu requisição no carregamento",
    "tabela": "registro completo da execução",
}

# Observação por dimensão: explica o que a dimensão cobre, no card.
OBSERVACOES = {
    "lgpd": ("Conformidade LGPD observável de fora (caixa-preta). Inclui os testes de "
             "acessibilidade, que contam também aqui — LBI, Art. 63."),
    "ux": "Acessibilidade conta aqui e em lgpd.",
    "verification": "A suíte testando a si mesma (tests/).",
    "load": "Carga só roda com autorização explícita (WEBQA_LOAD_AUTHORIZED).",
}

# Prosa do relatório em constantes de UMA linha, de propósito: quebra de linha
# dentro do HTML gerado colapsa no navegador mas quebra grep, teste e auditoria.
# O texto também fica auditável num lugar só.
NOTA_DUPLA = ("Um teste pode contar em mais de uma dimensão — acessibilidade conta em "
              "<code>ux</code> e em <code>lgpd</code> (LBI, Art. 63).")
ACHADOS_VAZIO = ("Nenhuma não conformidade observada nesta execução. Isso não é certificado: "
                 "o que não é observável por HTTP segue fora do alcance.")
ALERTAS_VAZIO = "Nenhum alerta: os sinais de maturidade observáveis estão presentes."
ALERTAS_INTRO = ("Vale a pena ter; não é ilegal não ter. <b>Nenhum alerta entra na contagem "
                 "de achados.</b>")
TERCEIROS_AUSENTE = ("Inventário não disponível: <code>report/terceiros.json</code> não foi "
                     "gerado (a execução não incluiu testes de navegador).")
TERCEIROS_VAZIO = ("Nenhum terceiro contactado no carregamento — todas as requisições ficaram "
                   "no próprio alvo.")
TERCEIROS_INTRO = ("Registro factual — não acusa nem absolve. Insumo de ROPA/DPA: cada host "
                   "recebeu o IP e o User-Agent do visitante.")
TABELA_VAZIA = "Nenhum resultado para listar."
TABELA_IMPRESSAO = ("Na versão impressa sem a tabela expandida, o registro completo está em "
                    "<code>report/summary.json</code>.")
RODAPE_SEM_SELO = ("Este documento registra observações de caixa-preta sobre o alvo. Não "
                   "constitui certificação, selo ou aprovação de conformidade.")

# Referências legais ganham destaque; o TEXTO vem do código, o design só apresenta.
_LEI = re.compile(r"(Art\.\s*\d+º?(?:,\s*[IVXLC]+)?(?:\s*(?:§|&sect;)\s*\d+º?)?|LBI[,;]?\s*Art\.\s*\d+)")


# ---------- Primitivas ----------

def esc(valor: object) -> str:
    """Escapa para HTML, incluindo aspas — dado nunca vira marcação."""
    return html.escape(str(valor), quote=True)


def numero(valor: float, casas: int = 2) -> str:
    """Número em pt-BR: vírgula decimal, como manda o contrato visual."""
    return f"{valor:.{casas}f}".replace(".", ",")


def duracao(segundos: float) -> str:
    return f"{numero(segundos, 3 if segundos < 1 else 1)} s"


def destaca_leis(texto_escapado: str) -> str:
    """Envolve referências legais em <strong class="lei">. Roda APÓS o escape."""
    return _LEI.sub(r'<strong class="lei">\1</strong>', texto_escapado)


def icone(estado: str) -> str:
    return ICONES.get(estado, "")


def estado_de(resultado: dict) -> str:
    """Estado visual do resultado: xfail é estado próprio, não um skip qualquer."""
    marcado = resultado.get("estado")
    if marcado in ROTULOS:
        return marcado
    return resultado.get("outcome", "skipped")


def _selo(estado: str, classe: str = "estado") -> str:
    """Forma + rótulo textual: distinguível sem cor, legível por leitor de tela."""
    return f'<span class="{classe} {estado}">{icone(estado)}{ROTULOS.get(estado, estado)}</span>'


def _versao() -> str:
    """Versão do pyproject — evita número de versão divergindo em dois lugares."""
    try:
        import tomllib

        dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
        return str(dados["project"]["version"])
    except Exception:
        return "1.0.0"


# ---------- Leitura dos dados ----------

def _contagem(resultados: list[dict]) -> Counter:
    return Counter(estado_de(r) for r in resultados)


def _por_dimensao(resultados: list[dict]) -> dict[str, list[dict]]:
    """Um teste multidimensional aparece em CADA dimensão que declarou."""
    agrupado: dict[str, list[dict]] = {}
    for r in resultados:
        for dim in r.get("dimensions") or [r.get("dimension", "other")]:
            agrupado.setdefault(dim, []).append(r)
    return agrupado


def _sem_navegador(resultados: list[dict]) -> list[dict]:
    return [r for r in resultados
            if r.get("browser") and estado_de(r) == "skipped"
            and "Chromium indispon" in (r.get("detail") or "")]


# ---------- Seções ----------

def _cabecalho(summary: dict, resultados: list[dict], contagem: Counter, indice: list[str]) -> str:
    total = len(resultados)
    navegador = sum(1 for r in resultados if r.get("browser"))
    itens = "".join(
        f'<span class="resumo-item {estado}{" zero" if not contagem.get(estado) else ""}">'
        f'{icone(estado)}<b>{contagem.get(estado, 0)}</b>'
        f'<span>{PLURAIS[estado]}</span></span>'
        for estado in ("failed", "xfail", "passed", "skipped")
    )
    meta = [("Gerado em", esc(summary.get("generated_at", "—"))),
            ("Duração", esc(duracao(float(summary.get("duration_s") or 0)))),
            ("Execução", f'<code>{esc(summary.get("comando", "pytest"))}</code>')]
    if summary.get("alvo"):
        meta.insert(0, ("Alvo", f'<code>{esc(summary["alvo"])}</code>'))
    linhas_meta = "".join(f"<div><dt>{r}</dt><dd>{v}</dd></div>" for r, v in meta)
    secoes = (
        ("panorama", "Panorama"),
        ("achados", f"Achados ({contagem.get('failed', 0)})"),
        ("alertas", f"Alertas ({contagem.get('xfail', 0)})"),
        ("terceiros", "Terceiros"),
        ("tabela", "Todos os resultados"),
    )
    navegacao = "".join(
        f'<a href="#{ancora}"><span class="n">{i}</span>{esc(rotulo)}</a>'
        for i, (ancora, rotulo) in enumerate(
            [(a, r) for a, r in secoes if a in indice], start=1))
    total_txt = (f"{total} testes · {navegador} de navegador · "
                 f"{esc(duracao(float(summary.get('duration_s') or 0)))} no total")
    return f"""<header>
  <div class="marca-linha">{MARCA}
    <span class="doc-tipo">Relatório por execução · report/summary.html</span></div>
  <h1>Relatório de Qualidade</h1>
  <dl class="meta">{linhas_meta}</dl>
  <p class="resumo" role="group" aria-label="Resumo da execução">{itens}
    <span class="resumo-total num">{total_txt}</span></p>
  <nav class="indice" aria-label="Seções do relatório">{navegacao}</nav>
</header>"""


def _avisos(resultados: list[dict], contagem: Counter, dimensoes: list[str]) -> str:
    """Variantes decididas por INSPEÇÃO dos results — nenhuma flag nova."""
    avisos = []
    pulados = _sem_navegador(resultados)
    if pulados:
        avisos.append(
            f'<p class="aviso">{icone("skipped")}<b>Chromium indisponível neste ambiente.</b> '
            f"{len(pulados)} testes de navegador foram pulados — o motivo consta em cada "
            "linha da tabela. Para habilitar: "
            "<code>python -m playwright install chromium</code>.</p>")
    if not resultados:
        avisos.append('<p class="aviso"><b>Nenhum resultado registrado.</b> A execução não '
                      "avaliou alvo algum — rode a suíte apontada para um alvo.</p>")
    elif len(dimensoes) == 1:
        avisos.append(f'<p class="aviso"><b>Execução parcial:</b> apenas a dimensão '
                      f"<code>{esc(dimensoes[0])}</code> foi executada. As demais não foram "
                      "avaliadas — ausência de achado aqui não é ausência de achado.</p>")
    if resultados and not contagem.get("failed"):
        avisos.append('<p class="aviso destaque">' + icone("passed") +
                      "<b>Nenhuma não conformidade observada nesta execução.</b> "
                      "Passar não certifica conformidade — ver a nota epistêmica.</p>")
    return "\n".join(avisos)


def _panorama(resultados: list[dict], notas: dict) -> str:
    legenda = "".join(f"<span>{_selo(estado, 'estado-min')}{esc(texto)}</span>"
                      for estado, texto in LEGENDA.items())
    agrupado = _por_dimensao(resultados)
    cards = []
    # A dimensão que carrega a nota epistêmica lidera o panorama (é o card largo,
    # como na referência): quem lê precisa encontrar a ressalva antes dos números.
    def ordem(dim: str) -> tuple:
        c = _contagem(agrupado[dim])
        return (0 if notas.get(dim) else 1, -c.get("failed", 0), dim)

    for dim in sorted(agrupado, key=ordem):
        itens = agrupado[dim]
        c = _contagem(itens)
        if c.get("failed"):
            veredito = f'{c["failed"]} {"achado" if c["failed"] == 1 else "achados"}'
            classe_veredito = "failed"
        elif not c.get("passed") and c.get("skipped"):
            # Só skip não é aprovação: dizer "sem achados" aqui seria mentira por
            # omissão — a dimensão não foi avaliada.
            veredito, classe_veredito = "não avaliada", "skipped"
        else:
            veredito, classe_veredito = "sem achados", "passed"
        if c.get("xfail"):
            veredito += f' · {c["xfail"]} {"alerta" if c["xfail"] == 1 else "alertas"}'
        contadores = "".join(
            f'<span class="ct {estado}{" zero" if not c.get(estado) else ""}">{icone(estado)}'
            f'{c.get(estado, 0)}<span class="sr"> {PLURAIS[estado]}</span></span>'
            for estado in ("failed", "xfail", "passed", "skipped"))
        observacao = (f'<p class="dim-obs">{esc(OBSERVACOES[dim])}</p>'
                      if dim in OBSERVACOES else "")
        nota = ""
        if notas.get(dim):
            nota = (f'<div class="nota-epistemica"><p class="nota-k">Nota epistêmica — '
                    f"vale para toda a dimensão</p><p>{esc(notas[dim])}</p>"
                    f'<p class="sem-selo">{esc(SEM_SELO)}</p></div>')
        cards.append(
            f'<div class="dim{" dim-" + esc(dim) if nota else ""}"><div>'
            f'<span class="dim-nome">{esc(dim)}</span>'
            f'<p class="dim-veredito {classe_veredito}">{esc(veredito)}</p>'
            f'<p class="cts">{contadores}</p>{observacao}</div>{nota}</div>')
    return f"""<section id="panorama">
  <div class="sec-h"><h2><span class="n">1</span>Panorama por dimensão</h2>
    <span class="sec-sub">{esc(SUBTITULOS["panorama"])}</span></div>
  <div class="dims">{"".join(cards)}</div>
  <p class="nota-dupla">{NOTA_DUPLA}</p>
  <p class="legenda" aria-label="Legenda dos estados">{legenda}</p>
</section>"""


def _bloco_achado(resultado: dict, identificador: str, estado: str) -> str:
    detalhe = destaca_leis(esc((resultado.get("detail") or "").strip() or "sem detalhe registrado"))
    dims = "".join(f'<span class="chip-dim">{esc(d)}</span>'
                   for d in (resultado.get("dimensions") or [resultado.get("dimension", "")]) if d)
    navegador = "<span>navegador</span>" if resultado.get("browser") else ""
    margem = (f'<span class="achado-id">{esc(identificador.upper())}</span>'
              if estado == "failed" else "")
    return f"""<article class="{"achado" if estado == "failed" else "alerta"}" id="{esc(identificador)}">
    <div class="achado-margem">{margem}{_selo(estado)}</div>
    <div><p class="detalhe">{detalhe}</p>
      <p class="achado-meta">{dims}<code>{esc(resultado.get("test", "?"))}</code>
        <span class="num">{esc(duracao(float(resultado.get("duration_s") or 0)))}</span>
        {navegador}</p></div>
  </article>"""


def _achados(resultados: list[dict], mapa: dict[str, str]) -> str:
    falhas = [r for r in resultados if estado_de(r) == "failed"]
    if not falhas:
        return """<section id="achados">
  <div class="sec-h"><h2><span class="n">2</span>Achados</h2></div>
  <p class="intro-sec vazio">{ACHADOS_VAZIO}</p>
</section>"""
    grupos: dict[str, list[dict]] = {}
    for r in falhas:
        grupos.setdefault(r.get("dimension", "other"), []).append(r)
    partes = []
    for dim in sorted(grupos, key=lambda d: (-len(grupos[d]), d)):
        itens = grupos[dim]
        extra = ""
        if any(len(r.get("dimensions") or []) > 1 for r in itens):
            outras = sorted({d for r in itens for d in (r.get("dimensions") or []) if d != dim})
            if outras:
                extra = f" · contam também em {', '.join(esc(o) for o in outras)} (LBI, Art. 63)"
        partes.append(f"<h3>{esc(dim)} — {len(itens)} "
                      f'{"achado" if len(itens) == 1 else "achados"}{extra}</h3>')
        partes += [_bloco_achado(r, mapa[id(r)], "failed") for r in itens]
    plural = "não conformidade observada" if len(falhas) == 1 else "não conformidades observadas"
    return f"""<section id="achados">
  <div class="sec-h"><h2><span class="n">2</span>Achados — {len(falhas)} {plural}</h2>
    <span class="sec-sub">{esc(SUBTITULOS["achados"])}</span></div>
  {"".join(partes)}
</section>"""


def _alertas(resultados: list[dict], mapa: dict[str, str]) -> str:
    alertas = [r for r in resultados if estado_de(r) == "xfail"]
    if not alertas:
        return """<section id="alertas">
  <div class="sec-h"><h2><span class="n">3</span>Alertas</h2></div>
  <p class="intro-sec vazio">{ALERTAS_VAZIO}</p>
</section>"""
    corpo = "".join(_bloco_achado(r, mapa[id(r)], "xfail") for r in alertas)
    plural = "sinal" if len(alertas) == 1 else "sinais"
    titulo = f"Alertas — {len(alertas)} {plural} de maturidade ausentes"
    return f"""<section id="alertas">
  <div class="sec-h"><h2><span class="n">3</span>{titulo}</h2>
    <span class="sec-sub">{esc(SUBTITULOS["alertas"])}</span></div>
  <p class="intro-sec">{ALERTAS_INTRO}</p>
  {corpo}
</section>"""


def _terceiros(inventario: dict | None, resultados: list[dict], allowlist: list[str],
               mapa: dict[str, str]) -> str:
    cabecalho = ('<section id="terceiros">\n  <div class="sec-h"><h2><span class="n">4</span>'
                 "Inventário de terceiros</h2>"
                 f'<span class="sec-sub">{esc(SUBTITULOS["terceiros"])}</span></div>')
    if inventario is None:
        return (cabecalho + f'\n  <p class="intro-sec vazio">{TERCEIROS_AUSENTE}</p>\n</section>')
    hosts = inventario.get("third_parties") or []
    if not hosts:
        return (cabecalho + f'\n  <p class="intro-sec vazio">{TERCEIROS_VAZIO}</p>\n</section>')
    linhas = []
    for terceiro in hosts:
        host = str(terceiro.get("host", "?"))
        tracker = is_tracker(f"https://{host}/", allowlist)
        chip = ('<span class="chip-tracker">consta em TRACKER_DOMAINS</span>' if tracker
                else '<span class="chip-neutro">não classificado</span>')
        referencia = "—"
        for r in resultados:
            if estado_de(r) == "failed" and host in (r.get("detail") or ""):
                marca = mapa[id(r)]
                referencia = f'ver <a href="#{esc(marca)}">{esc(marca.upper())}</a>'
                break
        linhas.append(
            f'<tr><td class="t-teste">{esc(host)}</td>'
            f'<td class="t-dur">{esc(terceiro.get("requests", 0))}</td>'
            f'<td>{esc(", ".join(terceiro.get("resource_types") or []))}</td>'
            f'<td>{chip}</td><td class="t-det">{referencia}</td></tr>')
    return f"""{cabecalho}
  <p class="intro-sec">{TERCEIROS_INTRO}</p>
  <div class="rolagem"><table>
    <caption class="sr">Hosts de terceiros contactados no carregamento</caption>
    <thead><tr><th scope="col">Host</th><th scope="col">Requisições</th>
      <th scope="col">Tipos de recurso</th><th scope="col">Classificação</th>
      <th scope="col">Observação</th></tr></thead>
    <tbody>{"".join(linhas)}</tbody>
  </table></div>
</section>"""


def _tabela(resultados: list[dict], contagem: Counter, mapa: dict[str, str]) -> str:
    if not resultados:
        return ('<section id="tabela">\n  <div class="sec-h"><h2><span class="n">5</span>'
                f'Todos os resultados</h2></div>\n  <p class="intro-sec vazio">'
                f"{TABELA_VAZIA}</p>\n</section>")
    linhas = []
    for r in resultados:
        estado = estado_de(r)
        motivo = "—"
        if estado == "failed":
            marca = mapa.get(id(r), "")
            motivo = f'ver <a href="#{esc(marca)}">{esc(marca.upper())}</a>' if marca else "—"
        elif r.get("detail"):
            motivo = esc((r["detail"] or "").strip()[:240])
        linhas.append(
            f'<tr class="{estado}"><td>{_selo(estado, "estado-min")}</td>'
            f'<td class="t-teste">{esc(r.get("dimension", "—"))}</td>'
            f'<td class="t-teste">{esc(r.get("test", "?"))}</td>'
            f'<td class="t-dur">{esc(duracao(float(r.get("duration_s") or 0)))}</td>'
            f'<td class="t-det">{motivo}</td></tr>')
    resumo = " · ".join(f"{contagem.get(e, 0)} {PLURAIS[e]}"
                       for e in ("failed", "xfail", "passed", "skipped") if contagem.get(e))
    return f"""<section id="tabela">
  <div class="sec-h"><h2><span class="n">5</span>Todos os resultados</h2>
    <span class="sec-sub">{esc(SUBTITULOS["tabela"])}</span></div>
  <details class="tabela-wrap">
    <summary>Abrir a tabela completa — {len(resultados)} resultados ({esc(resumo)})</summary>
    <div class="rolagem"><table>
      <caption class="sr">Todos os resultados da execução</caption>
      <thead><tr><th scope="col">Estado</th><th scope="col">Dimensão</th>
        <th scope="col">Teste</th><th scope="col">Duração</th>
        <th scope="col">Motivo / referência</th></tr></thead>
      <tbody>{"".join(linhas)}</tbody>
    </table></div>
  </details>
  <p class="intro-sec so-impressao">{TABELA_IMPRESSAO}</p>
</section>"""


def _rodape(summary: dict) -> str:
    comando = esc(summary.get("comando", "pytest"))
    gerado = (f'Gerado em {esc(summary.get("generated_at", "—"))} · registro completo em '
              f"<code>report/summary.json</code>.")
    return f"""<footer>
  <p><strong>WebQA Suite</strong> v{esc(_versao())} · relatório gerado automaticamente por
    <code>webqa/report.py</code> · comando: <code>{comando}</code></p>
  <p>{RODAPE_SEM_SELO}</p>
  <p>{gerado}</p>
</footer>"""


# ---------- Montagem ----------

def montar(summary: dict, terceiros: dict | None = None,
           allowlist: list[str] | None = None) -> str:
    """HTML completo: arquivo único, zero requisição externa, sem <script>."""
    resultados = list(summary.get("results") or [])
    contagem = _contagem(resultados)
    notas = summary.get("dimension_notes") or {}
    dimensoes = sorted(_por_dimensao(resultados))

    # Numeração estável A1…An / x1…xn na ordem em que os resultados chegaram.
    mapa: dict[int, str] = {}
    for indice, r in enumerate((r for r in resultados if estado_de(r) == "failed"), start=1):
        mapa[id(r)] = f"a{indice}"
    for indice, r in enumerate((r for r in resultados if estado_de(r) == "xfail"), start=1):
        mapa[id(r)] = f"x{indice}"

    secoes_indice = ["panorama", "achados", "alertas", "terceiros", "tabela"]
    titulo = esc(f"WebQA Suite — Relatório de Qualidade — {summary.get('generated_at', '')}")
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{titulo}</title>
<link rel="icon" href='{FAVICON}'>
<style>{ESTILO_CANONICO}</style></head>
<body>
<a class="pular" href="#achados">Ir direto aos achados</a>
<div class="folha">
{_cabecalho(summary, resultados, contagem, secoes_indice)}
{_avisos(resultados, contagem, dimensoes)}
<main>
{_panorama(resultados, notas)}
{_achados(resultados, mapa)}
{_alertas(resultados, mapa)}
{_terceiros(terceiros, resultados, allowlist or [], mapa)}
{_tabela(resultados, contagem, mapa)}
</main>
{_rodape(summary)}
</div>
</body></html>
"""
