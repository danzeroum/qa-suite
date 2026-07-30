"""Painel de estabilidade — `report/estabilidade.html` a partir do ledger.

Espelha `docs/qa-suite design brief/referencia/estabilidade.html`. Mesmas
restrições do `summary.html`, pelas mesmas razões: arquivo único, zero
requisição externa, íntegro sem JS, impressão de primeira classe, tema escuro
por `prefers-color-scheme` mais o gancho `[data-tema]`.

**Reusa `ESTILO_CANONICO` byte a byte** (regra 2.4). Não há classe nova aqui: as
42 classes que a referência usa já existem na folha — foi conferido, e há teste
fixando. Quando o painel precisou de algo, compôs com o que existe.

A separação com `scripts/estabilidade.py` é de camada: lá mora a REGRA (quem
conta, quem zera, quem só informa), aqui mora a APRESENTAÇÃO. O painel não
recalcula sequência — recebe a caminhada pronta. Duas implementações da mesma
regra divergem, e divergiriam justamente no número que a página exibe como
verdade.
"""
from __future__ import annotations

from webqa.report_html import esc, icone
from webqa.report_style import ESTILO_CANONICO, FAVICON, MARCA

META_PADRAO = 10

# Vocabulário de estado, reusado do relatório e não reinventado: noite limpa fala
# `passed`, flake fala `failed`, o que não conta fala `skipped`. O leitor que já
# viu um summary.html reconhece a forma antes de ler o rótulo — e cada estado
# leva forma + texto, nunca só cor (regra 2.5).
EFEITO_LIMPA = "passed"
EFEITO_FLAKE = "failed"
EFEITO_NEUTRO = "skipped"


def _linha_efeito(estado: str, texto: str) -> str:
    return f'<span class="estado-min {estado}">{icone(estado)}{esc(texto)}</span>'


def _sha_curto(sha: str) -> str:
    return f"{sha[:8]}…{sha[-8:]}" if len(sha) > 20 else sha


def classificar_linhas(execucoes: list[dict], passos: list) -> list[dict]:
    """Uma linha de tabela por entrada do ledger, da mais recente para a mais antiga.

    Toda entrada aparece. Nenhuma é removida — nem a `ci` anterior à emenda, nem
    a que ficou em quarentena. O ledger é registro auditável: apagar o que não
    conta transformaria "não pontuou" em "nunca existiu", e a diferença entre as
    duas é justamente o que um caderno de bordo precisa preservar.
    """
    por_id = {id(p.entrada): p for p in passos}
    linhas = []
    for entrada in execucoes:
        passo = por_id.get(id(entrada))
        origem = str(entrada.get("origem") or "local")
        flakes = int(entrada.get("infra_flakes", 0) or 0)

        # A ordem das checagens é a ordem do motivo PRINCIPAL, não a ordem em que
        # o classificador filtra. Uma entrada pode ser `ci` E estar em quarentena
        # — é o caso da única entrada real do ledger hoje. Rotulá-la de
        # "quarentena" esconderia o motivo que basta sozinho: ela não veio do
        # ambiente oficial, e nem um juiz perfeito a faria pontuar.
        if passo is not None and passo.limpa:
            estado, texto = EFEITO_LIMPA, f"limpa · sequência: {passo.streak}"
        elif passo is not None:
            estado, texto = EFEITO_FLAKE, "flake · sequência zerada"
        elif origem == "ci":
            estado, texto = EFEITO_NEUTRO, "histórico · anterior à emenda — não conta"
        elif origem != "vps":
            estado, texto = EFEITO_NEUTRO, "informativa · não conta"
        elif _em_quarentena(entrada):
            # Só aqui a quarentena é a explicação: entrada `vps`, que contaria se
            # o juiz que a produziu fosse confiável.
            estado, texto = EFEITO_NEUTRO, "quarentena · juiz com defeito — não conta, não zera"
        else:
            estado, texto = EFEITO_NEUTRO, "não conta · segunda execução do dia UTC"

        if passo is not None and passo.alvo_mudou:
            texto += " · o alvo mudou de identidade"

        # "1 — TimeoutError" diz o que houve; "1" manda o leitor abrir o log.
        # Entrada anterior ao schema 5 não tem as assinaturas e mostra só a
        # contagem: campo ausente não vira texto inventado.
        assinaturas = [str(a) for a in (entrada.get("infra_assinaturas") or [])]
        flakes_texto = f"{flakes} — {', '.join(assinaturas)}" if assinaturas else str(flakes)

        quando = str(entrada.get("generated_at") or entrada.get("dia_utc") or "—")
        linhas.append({
            "quando": quando,
            "dia": str(entrada.get("dia_utc") or quando[:10]),
            "hora": quando[11:] or "00:00:00",
            "origem": origem,
            "conta": passo is not None,
            "browser_total": int(entrada.get("browser_total", 0) or 0),
            "flakes": flakes,
            "flakes_texto": flakes_texto,
            "estado": estado,
            "efeito": texto,
            "alvo_sha256": str(entrada.get("alvo_sha256") or ""),
        })
    # Dias do mais recente para o mais antigo; DENTRO do dia, do mais antigo
    # para o mais novo. Não é inconsistência: a que vale é a PRIMEIRA do dia, e
    # ela precisa encabeçar o grupo — a segunda execução pendura embaixo como
    # nota de rodapé daquele dia. Invertido, o leitor veria "não conta" antes de
    # saber o que contou. Dois `sort` porque o de Python é estável.
    linhas.sort(key=lambda linha: linha["hora"])
    linhas.sort(key=lambda linha: linha["dia"], reverse=True)
    return linhas


def _em_quarentena(entrada: dict) -> bool:
    # Import tardio: `webqa/` é biblioteca e `scripts/` é consumidor, então a
    # dependência só existe no ponto onde é inevitável — a regra de quarentena
    # mora com o classificador, e duplicá-la aqui seria criar a segunda fonte
    # que este módulo inteiro existe para evitar.
    from scripts.estabilidade import em_quarentena

    return em_quarentena(entrada)


def _slots(streak: int, meta: int) -> str:
    partes = []
    for i in range(meta):
        classes = "slot"
        if i < streak:
            classes += " ok"
        if i == meta - 1:
            classes += " meta-slot"
        titulo = f' title="{meta}ª noite: Fase 2"' if i == meta - 1 else ""
        partes.append(f'<span class="{classes}"{titulo}></span>')
    return "".join(partes)


def _historia(violacoes: int) -> str:
    """A história em um parágrafo, para quem nunca viu o projeto.

    O número de violações vem INTERPOLADO do contrato do alvo fixture, nunca
    literal: o fixture já ganhou violações uma vez (o `alvo_sha256` mudou por
    causa disso), e um literal aqui envelheceria em silêncio dentro de um
    parágrafo que ninguém relê.
    """
    return (
        "Toda noite, um robô inspeciona um site de teste cheio de erros conhecidos. "
        "Um auditor confere se o equipamento funcionou. Dez noites limpas seguidas "
        "liberam a próxima fase. Esta página é o caderno de bordo dessa contagem."
        f'</p>\n<p class="intro-sec">O site de teste reprova de propósito — '
        f"{violacoes} não conformidades fabricadas, declaradas em contrato. "
        "Reprovar o alvo é o robô funcionando; o que zera a contagem é o "
        "<strong>equipamento</strong> falhar. Por isso um relatório cheio de achados "
        "e uma sequência verde convivem: é o estado saudável do sistema."
    )


def motivos_do_zero(execucoes: list[dict], passos: list, sha_do_alvo_atual: str = "") -> list[str]:
    """Por que a sequência está em zero — derivado do ledger, não escrito à mão.

    Exibir "0/10" sem dizer por quê ensina o leitor a desconfiar do número. Pior:
    zero por *ainda não haver noite oficial* e zero por *flake ontem à noite* são
    situações opostas — a primeira é normal, a segunda é infraestrutura
    quebrando — e o mesmo dígito representa as duas.

    Os motivos são cumulativos de propósito: o ledger real hoje tem três ao
    mesmo tempo, e mostrar só o primeiro esconderia que corrigir a origem não
    bastaria para a contagem começar.
    """
    if not execucoes:
        return []                          # instalação nova tem texto próprio
    if passos and passos[-1].streak > 0:
        return []

    motivos = []
    fora_do_oficial = [e for e in execucoes if e.get("origem") != "vps"]
    if len(fora_do_oficial) == len(execucoes):
        origens = sorted({str(e.get("origem") or "local") for e in execucoes})
        rotulos = ", ".join(f"<code>{esc(o)}</code>" for o in origens)
        sujeito = ("a única entrada do ledger é" if len(execucoes) == 1
                   else f"as {len(execucoes)} entradas do ledger são")
        motivos.append(
            f"Nenhuma noite do ambiente oficial: {sujeito} de origem {rotulos}, "
            "que informa e não pontua." if len(execucoes) == 1 else
            f"Nenhuma noite do ambiente oficial: {sujeito} de origem {rotulos}, "
            "que informam e não pontuam.")

    em_quarentena = [e for e in execucoes if _em_quarentena(e)]
    if em_quarentena:
        uma = len(em_quarentena) == 1
        motivos.append(
            f"{len(em_quarentena)} {'entrada' if uma else 'entradas'} em "
            f"<strong>quarentena</strong>: {'julgada' if uma else 'julgadas'} por uma "
            "versão do classificador com defeito conhecido. "
            f"{'Não conta' if uma else 'Não contam'} e <strong>"
            f"{'não zera' if uma else 'não zeram'}</strong> — a execução pode ter sido "
            "boa, e não há como saber.")

    shas_no_ledger = {str(e.get("alvo_sha256") or "") for e in execucoes}
    if sha_do_alvo_atual and sha_do_alvo_atual not in shas_no_ledger:
        motivos.append(
            "O <strong>alvo mudou de identidade</strong> desde a última entrada: o "
            f"ledger conhece <code>{esc(_sha_curto(next(iter(sorted(shas_no_ledger)))))}</code> "
            f"e o alvo de hoje é <code>{esc(_sha_curto(sha_do_alvo_atual))}</code>. "
            "A sequência é por alvo, então recomeça — nove noites limpas contra um "
            "alvo mais uma contra outro não são dez noites limpas contra nada.")

    if passos and not passos[-1].limpa:
        motivos.append(
            "A última noite contada teve <strong>flake de infraestrutura</strong>: o "
            "equipamento falhou, e é isso — não o veredito sobre o alvo — que zera.")
    return motivos


def _bloco_do_zero(motivos: list[str]) -> str:
    if not motivos:
        return ""
    itens = "".join(f"<li>{m}</li>" for m in motivos)
    plural = "o motivo" if len(motivos) == 1 else f"os {len(motivos)} motivos"
    return (f'<div class="marco"><span class="marco-k">Por que a contagem está em '
            f'zero — {plural}</span>\n<ul>{itens}</ul>\n'
            '<p class="intro-sec">Zero aqui não é defeito da suíte nem do alvo: é '
            'ausência de evidência do ambiente oficial. Enquanto os motivos acima '
            'valerem, a contagem não começa — e começar antes seria contar noite que '
            'ninguém observou.</p></div>')


def _nota_de_alvo(linhas: list[dict], passos: list) -> str:
    """Aviso de troca de identidade do alvo, quando houver."""
    shas = {linha["alvo_sha256"] for linha in linhas if linha["alvo_sha256"]}
    if len(shas) < 2 and not any(p.alvo_mudou for p in passos):
        return ""
    return (
        '<p class="intro-sec"><strong>O alvo mudou de identidade.</strong> A sequência '
        "é por alvo: quando o <code>alvo_sha256</code> muda, ela recomeça — nove noites "
        "limpas contra um alvo mais uma contra outro não são dez noites limpas contra "
        "nada. As entradas do alvo anterior continuam abaixo, rotuladas como histórico: "
        "elas não pontuam, e não são apagadas.</p>"
    )


def _tabela(linhas: list[dict]) -> str:
    if not linhas:
        return (
            '<p class="intro-sec">O ledger ainda não tem nenhuma entrada. Isto é uma '
            "instalação nova, não um defeito: a primeira noite entra quando o cron do "
            "container da VPS rodar pela primeira vez. Até lá a contagem fica em zero "
            "porque não há evidência, e ausência de evidência não vira crédito.</p>"
        )
    corpo = "".join(
        f'<tr class="{"" if linha["estado"] == EFEITO_LIMPA else esc(linha["estado"])}">'
        f'<td class="t-teste num">{esc(linha["quando"])}</td>'
        f'<td><span class="origem{"" if linha["conta"] else " nao-conta"}">'
        f'{esc(linha["origem"])}</span></td>'
        f'<td class="t-dur">{linha["browser_total"]}</td>'
        f'<td class="t-det">{esc(linha["flakes_texto"])}</td>'
        f'<td class="t-efeito">{_linha_efeito(linha["estado"], linha["efeito"])}</td>'
        "</tr>"
        for linha in linhas
    )
    return f"""<div class="rolagem">
<table>
<caption class="sr">Entradas do ledger de estabilidade, da mais recente para a mais antiga</caption>
<thead><tr><th scope="col">Noite (UTC)</th><th scope="col">Origem</th>\
<th scope="col">Testes de navegador</th><th scope="col">Flakes de infra</th>\
<th scope="col">Efeito na sequência</th></tr></thead>
<tbody>{corpo}</tbody>
</table>
</div>"""


def montar(ledger: dict, passos: list, violacoes_do_contrato: int,
           meta: int = META_PADRAO, ledger_path: str = "docs/lgpd-estabilidade.json",
           sha_do_alvo_atual: str = "") -> str:
    """HTML completo do painel. Arquivo único, sem requisição externa.

    `sha_do_alvo_atual` é a identidade do alvo de HOJE, que o painel compara com
    a do ledger para dizer se a sequência recomeçou. Vazio quando o chamador não
    consegue resolvê-la — e aí o motivo simplesmente não é afirmado, em vez de
    ser chutado.
    """
    execucoes = list(ledger.get("execucoes") or [])
    linhas = classificar_linhas(execucoes, passos)
    streak = passos[-1].streak if passos else 0
    dias = len(passos)
    sha_atual = next((linha["alvo_sha256"] for linha in linhas if linha["alvo_sha256"]), "")

    plural = "uma entrada" if len(execucoes) == 1 else f"{len(execucoes)} entradas"
    titulo = esc("WebQA Suite — Painel de Estabilidade — dimensão lgpd")
    alvo_cell = (
        f'<code title="fixture_target:{esc(sha_atual)}">fixture_target:'
        f"{esc(_sha_curto(sha_atual))}</code>" if sha_atual else "<code>—</code>"
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{titulo}</title>
<link rel="icon" href='{FAVICON}'>
<style>{ESTILO_CANONICO}</style></head>
<body>
<a class="pular" href="#progresso">Ir direto ao progresso</a>
<div class="folha">
<header>
  <div class="marca-linha">
    {MARCA}</span>
    <span class="doc-tipo">Caderno de bordo · {esc(ledger_path)}</span>
  </div>
  <h1>Painel de Estabilidade</h1>
  <p class="alvo-sub">Dimensão <strong>lgpd</strong> · a infraestrutura de navegador \
sob observação, noite após noite</p>
  <dl class="meta"><div><dt>Ledger</dt><dd><code>{esc(ledger_path)}</code></dd></div>\
<div><dt>Meta</dt><dd class="num">{meta} noites limpas consecutivas</dd></div>\
<div><dt>Ambiente oficial</dt><dd>container da VPS (<code>WEBQA_ORIGEM=vps</code>)</dd></div>\
<div><dt>Alvo</dt><dd class="num">{alvo_cell}</dd></div></dl>
  <nav class="indice" aria-label="Seções"><a href="#progresso"><span class="n">1</span>Progresso</a>\
<a href="#regras"><span class="n">2</span>Regras</a>\
<a href="#linha-do-tempo"><span class="n">3</span>Linha do tempo</a></nav>
</header>
<main>

<section id="progresso" aria-labelledby="h-progresso">
<div class="sec-h"><h2 id="h-progresso"><span class="n">1</span>Progresso rumo à Fase 2</h2>\
<span class="sec-sub">{meta} noites limpas consecutivas destravam os testes ativos</span></div>
<p class="historia">{_historia(violacoes_do_contrato)}</p>
<div class="progresso">
<div><p class="prog-num num">{streak}<small>/{meta}</small></p>\
<p class="prog-rot">noites limpas consecutivas · origem vps</p></div>
<div class="slots" role="img" aria-label="{streak} de {meta} noites limpas">
{_slots(streak, meta)}
</div>
</div>
{_bloco_do_zero(motivos_do_zero(execucoes, passos, sha_do_alvo_atual))}
<div class="marco">
<span class="marco-k">O que acontece em {meta}/{meta}</span>
<p><strong>FASE 2 DESTRAVADA</strong> — testes ativos de consentimento (aceitar/recusar o
banner e comparar antes/depois), atrás do gate próprio
<code>WEBQA_ACTIVE_PROBES_AUTHORIZED=1</code>. Sem troféu: a sequência é critério de
engenharia, não gamificação.</p>
</div>
</section>

<section id="regras" aria-labelledby="h-regras">
<div class="sec-h"><h2 id="h-regras"><span class="n">2</span>O que zera, o que não zera</h2>\
<span class="sec-sub">a distinção que dá sentido à métrica</span></div>
<div class="regras">
<div class="regra zera"><h3>{icone("failed")} Zera a sequência</h3><p>Flake de
infraestrutura: <code>TimeoutError</code>, <code>TargetClosed</code>, <code>net::ERR_*</code>,
Chromium ausente. O equipamento falhou — a noite não conta e a contagem volta a zero.</p></div>
<div class="regra avanca"><h3>{icone("passed")} Não zera — avança</h3><p>FAIL determinístico
do alvo: tracker antes do consentimento, cookie de 730 dias, violação axe. A suíte
funcionou; quem está errado é o alvo.</p></div>
<div class="regra neutra"><h3>{icone("skipped")} Não conta</h3><p>Origem <code>ci</code> ou
<code>local</code> (fora do ambiente oficial), segunda execução no mesmo dia UTC, execução
sem testes de navegador, entrada em quarentena por versão do classificador. Nem avança,
nem zera.</p></div>
</div>
<p class="intro-sec">A sequência é recalculada do histórico inteiro a cada rodada e é
<strong>por alvo</strong>: se o <code>alvo_sha256</code> mudar, recomeça. Origem desconhecida
degrada para <code>local</code> — no pior caso deixa de contar, nunca conta errado.</p>
</section>

<section id="linha-do-tempo" aria-labelledby="h-linha-do-tempo">
<div class="sec-h"><h2 id="h-linha-do-tempo"><span class="n">3</span>Linha do tempo do ledger</h2>\
<span class="sec-sub">{esc(ledger_path)} · {plural} · {dias} contada(s) na sequência</span></div>
{_nota_de_alvo(linhas, passos)}
{_tabela(linhas)}
<p class="intro-sec">Datas em dia UTC; vale a primeira execução do dia. Entradas
<code>ci</code> e <code>local</code> permanecem no ledger para auditoria — informam, não
pontuam.</p>
</section>
</main>
<footer>
<p><strong>WebQA Suite</strong> · painel gerado a partir de <code>{esc(ledger_path)}</code>
por <code>scripts/estabilidade.py</code> · único escritor do ledger: container da VPS ·
GitHub roda apenas smoke-test com <code>--dry-run</code></p>
<p><code>WEBQA_ORIGEM</code> é declaração do ambiente, não prova criptográfica — a barreira
existe contra descuido, não contra falsificação deliberada.</p>
</footer>
</div>
</body></html>
"""
