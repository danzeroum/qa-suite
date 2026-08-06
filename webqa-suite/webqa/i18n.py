"""Internacionalização: o layout aguenta outro idioma? (GUI-RESP i18n/RTL, OS-52)

Duas perguntas que nenhum alvo monolíngue responde sozinho:

* **RTL** — em árabe ou hebraico a página inteira espelha. Layout preso a
  `left`/`margin-left` em vez de `start`/`margin-inline-start` colapsa ou
  extravasa, e ninguém percebe até traduzir;
* **expansão de texto** — do inglês para o alemão ou o português o texto cresce
  de 30% a 100%. Botão dimensionado no texto mais curto corta o rótulo no
  primeiro idioma que expandir.

**Pseudo-localização, e por que ela é passiva.** As duas manipulações acontecem
no CLIENTE, por `evaluate`: `dir=rtl` no `<html>` e o texto visível alongado. O
alvo não recebe requisição nova, não recebe formulário, não recebe nada — é a
mesma classe de `page.route` da OS-47, e o gate C2 segue intocado. Nada disso
persiste: morre com o contexto.

**O que NÃO expande, e o motivo de a lista existir.** Expandir tudo produziria
achado falso em massa: campo de formulário tem tamanho de dado e não de texto,
número expandido vira número errado, e conteúdo `aria-hidden` não é lido por
ninguém. A lista é curta, declarada e testada — heurística que expande demais
reprova alvo conforme, e falso positivo em bateria custa a credibilidade da
bateria inteira.

Núcleo PURO: recebe descritores de nó e decide. Somente stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass

# 1,5 é a régua de mercado para "quanto o texto cresce ao traduzir": o guia da
# W3C e os guias de i18n da indústria usam 30%–100% conforme o comprimento da
# string, e 50% é o meio dessa faixa. Não é número da casa, e mudá-lo aqui faria
# a medida deixar de ser comparável com o que qualquer equipe de localização usa.
FATOR_PADRAO = 1.5

# Tags cujo conteúdo NÃO é texto de interface. `input`/`textarea`/`select`
# carregam DADO (um CEP expandido é um CEP errado); `code`/`kbd`/`samp`/`pre`
# carregam literal; `script`/`style` não são conteúdo.
TAGS_QUE_NAO_EXPANDEM = frozenset({
    "input", "textarea", "select", "option", "code", "kbd", "samp", "pre",
    "script", "style", "template", "svg", "math", "time",
})

# Caractere de alongamento. Letra latina comum de propósito: um caractere exótico
# mudaria a métrica da fonte e mediria falta de glifo em vez de largura de texto
# — o defeito seria real, mas seria outro, e o laudo diria o nome errado.
PREENCHIMENTO = "a"


@dataclass(frozen=True)
class No:
    """O que o navegador contou sobre um nó de texto, para a decisão ser pura."""

    tag: str
    texto: str
    aria_hidden: bool = False
    editavel: bool = False
    so_numero: bool = False


def deve_expandir(no: No) -> bool:
    """Este nó participa da expansão?

    Ordem das recusas por frequência do caso real, não por elegância: campo de
    formulário e conteúdo escondido são o que mais aparece.
    """
    if no.tag.lower() in TAGS_QUE_NAO_EXPANDEM:
        return False
    if no.aria_hidden or no.editavel or no.so_numero:
        return False
    return bool((no.texto or "").strip())


def expandir(texto: str, fator: float = FATOR_PADRAO) -> str:
    """O texto alongado no fator pedido, preservando o original como prefixo.

    Preserva o original para que o laudo continue legível: um botão que estourou
    ainda mostra qual botão era. Alongar por repetição do texto inteiro daria
    palavras diferentes e mediria quebra de linha em vez de largura.

    **A borda de um caractere.** `"a"` com fator 1,5 daria 1,5 caracteres, e
    `int()` truncaria de volta para 1 — a expansão não aconteceria, e o teste
    passaria anunciando que mediu. Arredonda-se para CIMA: expandir precisa
    expandir, ainda que por um caractere.
    """
    limpo = texto or ""
    if not limpo.strip():
        return limpo
    alvo = -(-len(limpo) * int(fator * 100) // 100)   # ceil sem importar math
    faltando = max(1, alvo - len(limpo))
    return limpo + PREENCHIMENTO * faltando


@dataclass(frozen=True)
class Quebra:
    """Um elemento que não sobreviveu à manipulação."""

    seletor: str
    motivo: str
    px: float = 0.0

    def __str__(self) -> str:
        detalhe = f" ({self.px:.0f}px)" if self.px else ""
        return f"{self.seletor}: {self.motivo}{detalhe}"


def quebras_de(brutos) -> tuple[Quebra, ...]:
    """Traduz o que o navegador devolveu. Tolerante: instrumentação ilegível não
    pode derrubar a observação do alvo."""
    return tuple(
        Quebra(seletor=str(b.get("seletor") or "?"),
               motivo=str(b.get("motivo") or "sem motivo declarado"),
               px=float(b.get("px") or 0.0))
        for b in (brutos or [])
    )


def resumo_de_quebras(quebras, teto: int = 10) -> str:
    """As maiores primeiro: quem for corrigir começa pela que mais extravasa."""
    ordenadas = sorted(quebras, key=lambda q: q.px, reverse=True)
    linhas = [f"  {q}" for q in ordenadas[:teto]]
    if len(ordenadas) > teto:
        linhas.append(f"  … e mais {len(ordenadas) - teto}")
    return "\n".join(linhas)


# ---------- forced-colors ----------

@dataclass(frozen=True)
class Distintivo:
    """Um elemento e como ele se distingue dos vizinhos, nos dois modos."""

    seletor: str
    fundo_normal: str
    fundo_forcado: str
    borda_normal: str
    borda_forcada: str
    fundo_de_referencia_normal: str
    fundo_de_referencia_forcado: str
    tem_texto_proprio: bool = False


def _tem_borda(valor: str) -> bool:
    return bool((valor or "").strip()) and (valor or "").strip() not in ("none", "0px none")


# Um fundo TRANSPARENTE não distingue nada: o elemento mostra o que estiver
# atrás dele. A primeira versão comparava o fundo próprio com o fundo EFETIVO do
# entorno, e como o próprio é `rgba(0, 0, 0, 0)` e o efetivo é branco, os dois
# diferiam — todo elemento sem fundo virava "distinguido por cor". A medição
# devolveu 12 perdas na home do alvo fabricado, e o laudo denunciou o defeito
# citando o próprio valor: `distinguia-se do entorno só por fundo (rgba(0,0,0,0))`.
_TRANSPARENTES = ("rgba(0, 0, 0, 0)", "transparent", "")


def _tem_fundo(valor: str) -> bool:
    return (valor or "").strip() not in _TRANSPARENTES


def _distinguia_por_cor(d: Distintivo) -> bool:
    """No modo normal, este elemento se destacava do entorno por cor?

    Fundo PINTADO e diferente do entorno, ou borda desenhada — as duas formas de
    "isto aqui é diferente" que o modo forçado sobrescreve. Fundo transparente
    não conta: não distinguir nada não é distintivo a perder.
    """
    fundo = _tem_fundo(d.fundo_normal) and d.fundo_normal != d.fundo_de_referencia_normal
    return fundo or _tem_borda(d.borda_normal)


def perdeu_informacao(d: Distintivo) -> bool:
    """O distintivo era SÓ cor e sumiu no modo forçado?

    **Mudar de cor não é perder informação — mudar de cor é o que o modo faz.**
    O que se acusa é outra coisa: um elemento que no modo normal se destacava dos
    vizinhos por fundo ou borda, e que no modo forçado passou a ser
    indistinguível deles. Aí a informação que a cor carregava não foi
    substituída por nada, e quem depende de alto contraste deixa de recebê-la.

    Elemento com TEXTO próprio está isento: o texto sobrevive ao modo forçado e
    continua carregando o significado. É a mesma regra da WCAG 1.4.1 aplicada ao
    inverso — cor não pode ser o único portador, e quando não é, o modo forçado
    não tira nada.
    """
    if d.tem_texto_proprio:
        return False
    if not _distinguia_por_cor(d):
        return False
    virou_igual = (not _tem_fundo(d.fundo_forcado)
                   or d.fundo_forcado == d.fundo_de_referencia_forcado)
    return virou_igual and not _tem_borda(d.borda_forcada)


def informacao_perdida(distintivos) -> tuple[Distintivo, ...]:
    """Os que perderam o único distintivo que tinham. Puro."""
    return tuple(d for d in distintivos if perdeu_informacao(d))


def relato_de_perdas(perdidos) -> str:
    """Nomeia o elemento E o distintivo perdido — sem os dois não há o que corrigir."""
    linhas = []
    for d in perdidos:
        o_que = ("fundo" if d.fundo_normal != d.fundo_de_referencia_normal else "borda")
        antes = d.fundo_normal if o_que == "fundo" else d.borda_normal
        linhas.append(f"  {d.seletor}: distinguia-se do entorno só por {o_que} ({antes}); "
                      f"sob forced-colors virou indistinguível dos vizinhos, e nada "
                      f"substituiu a informação que a cor carregava.")
    return "\n".join(linhas)


# ---------- coletores (JS) ----------

# Aplica a pseudo-localização e devolve quem quebrou. Roda DEPOIS de
# `document.fonts.ready`: fonte que chega tarde re-quebra o texto e muda a
# largura, e medir antes é medir uma página que o visitante nunca vê — a mesma
# disciplina de `checks/gui/test_reflow.py::_abrir_e_estabilizar`.
#
# A lista do que NÃO expandir é injetada de `TAGS_QUE_NAO_EXPANDEM`: a decisão
# mora no Python puro e testável, e o JS só a executa. Duas listas divergiriam.
JS_PSEUDO_LOCALIZAR = """
(cfg) => {
  const proibidas = new Set(cfg.tags);
  const larguraDoc = document.documentElement.clientWidth;
  const antes = new Map();
  for (const el of document.querySelectorAll('body *')) {
    const c = el.getBoundingClientRect();
    if (c.width > 0 && c.height > 0) { antes.set(el, {w: c.width, h: c.height}); }
  }
  if (cfg.rtl) { document.documentElement.setAttribute('dir', 'rtl'); }
  if (cfg.fator > 1) {
    const andar = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nos = [];
    while (andar.nextNode()) { nos.push(andar.currentNode); }
    for (const no of nos) {
      const pai = no.parentElement;
      if (!pai) { continue; }
      const tag = pai.tagName.toLowerCase();
      if (proibidas.has(tag)) { continue; }
      if (pai.closest('[aria-hidden="true"]') || pai.isContentEditable) { continue; }
      const txt = no.nodeValue || '';
      if (!txt.trim() || /^[\\d\\s.,:%+-]+$/.test(txt)) { continue; }
      const alvo = Math.ceil(txt.length * cfg.fator);
      no.nodeValue = txt + 'a'.repeat(Math.max(1, alvo - txt.length));
    }
  }
  const quebras = [];
  const nome = (el) => el.tagName.toLowerCase()
      + (el.id ? '#' + el.id : '')
      + (el.className && typeof el.className === 'string'
         ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  for (const [el, era] of antes) {
    const c = el.getBoundingClientRect();
    // EXTRAVASA: saiu da viewport na horizontal. Sob RTL o lado que estoura é o
    // esquerdo, e por isso os dois lados são medidos.
    const fora = Math.max(0, -c.left, c.right - larguraDoc);
    if (fora > cfg.tolerancia_px) {
      quebras.push({seletor: nome(el), motivo: 'extravasa a viewport', px: fora});
      continue;
    }
    // COLAPSA: tinha caixa e deixou de ter. Elemento que some ao espelhar ou ao
    // expandir levou o conteúdo junto.
    if (era.w > 0 && era.h > 0 && (c.width === 0 || c.height === 0)) {
      quebras.push({seletor: nome(el), motivo: 'colapsou (largura ou altura zero)', px: era.w});
      continue;
    }
    // CORTA: o conteúdo ficou maior que a caixa e a caixa esconde. Continua no
    // DOM — um teste que só olhasse o DOM aprovaria — e não está legível.
    const estilo = getComputedStyle(el);
    if (estilo.overflow === 'hidden' || estilo.overflowX === 'hidden') {
      const sobra = el.scrollWidth - el.clientWidth;
      if (sobra > cfg.tolerancia_px) {
        quebras.push({seletor: nome(el), motivo: 'texto cortado por overflow:hidden',
                      px: sobra});
      }
    }
  }
  return quebras;
}
"""

# Coleta os distintivos de cor de cada elemento, comparando com o ENTORNO (o
# fundo efetivo do pai). É o entorno que define "destacar-se": um fundo cinza
# numa página cinza não distingue nada, e o mesmo cinza numa página branca sim.
JS_DISTINTIVOS = """
() => {
  const efetivo = (el) => {
    let no = el;
    while (no) {
      const c = getComputedStyle(no).backgroundColor;
      if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') { return c; }
      no = no.parentElement;
    }
    return 'rgb(255, 255, 255)';
  };
  const nome = (el) => el.tagName.toLowerCase()
      + (el.id ? '#' + el.id : '')
      + (el.className && typeof el.className === 'string'
         ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const fora = [];
  for (const el of document.querySelectorAll('body *')) {
    const c = el.getBoundingClientRect();
    if (c.width <= 0 || c.height <= 0) { continue; }
    const e = getComputedStyle(el);
    // Texto PRÓPRIO: o que este elemento escreve, não o que os filhos escrevem.
    const proprio = [...el.childNodes]
        .filter(n => n.nodeType === 3).map(n => n.nodeValue.trim()).join('');
    fora.push({
      seletor: nome(el),
      fundo: e.backgroundColor,
      borda: e.borderStyle === 'none' ? '' : (e.borderStyle + ' ' + e.borderColor),
      entorno: el.parentElement ? efetivo(el.parentElement) : 'rgb(255, 255, 255)',
      tem_texto_proprio: proprio.length > 0,
    });
  }
  return fora;
}
"""


def distintivos_de(normal, forcado) -> tuple[Distintivo, ...]:
    """Casa as duas coletas POR SELETOR e monta os pares comparáveis.

    Elemento presente num modo e ausente no outro é descartado sem alarde: o
    modo forçado pode reflowar e mudar o que está visível, e acusar essa
    diferença mediria o reflow, não a perda de informação.
    """
    por_seletor = {d["seletor"]: d for d in (forcado or [])}
    pares = []
    for d in (normal or []):
        outro = por_seletor.get(d["seletor"])
        if outro is None:
            continue
        pares.append(Distintivo(
            seletor=d["seletor"],
            fundo_normal=d["fundo"], fundo_forcado=outro["fundo"],
            borda_normal=d["borda"], borda_forcada=outro["borda"],
            fundo_de_referencia_normal=d["entorno"],
            fundo_de_referencia_forcado=outro["entorno"],
            tem_texto_proprio=bool(d["tem_texto_proprio"]),
        ))
    return tuple(pares)
