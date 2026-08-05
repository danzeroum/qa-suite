"""Geometria da interface renderizada — o núcleo puro dos checks de `gui`.

Vive aqui, e não dentro dos checks, por duas razões que se reforçam: a lei da
casa (`checks/` só conhece fixtures, o detalhe mora em `webqa/` —
`docs/ARQUITETURA.md`) e o gate de complexidade, que vale em `webqa/` e é
dispensado em `checks/**` (`pyproject.toml`). Um algoritmo escrito dentro do
check escaparia do gate; aqui ele é obrigado a se decompor — e, decomposto, fica
testável sobre caixas fabricadas, sem subir navegador.

O miolo é a WCAG 2.5.8 (Target Size, Minimum), critério novo da 2.2. Ela **não**
diz "todo alvo tem 24px": diz que alvos menores são conformes quando cai uma de
suas exceções. Ignorá-las produziria reprovação em massa em qualquer site com
links dentro de texto — e falso positivo numa bateria de acessibilidade custa a
credibilidade da bateria inteira, que é o mesmo argumento com que
`webqa/sanitize.py` recusa detecção por entropia.

As três exceções automatizáveis, e o que cada uma exige de evidência:

* **inline** — o alvo está dentro de uma frase; o tamanho é imposto pela
  entrelinha do texto, não escolhido pelo autor. Vem do DOM (há texto irmão);
* **equivalente** — a mesma ação existe em outro controle conforme na página.
  Vem da identidade da ação (href, action, nome acessível);
* **espaçamento** — um círculo de 24px centrado no alvo não intersecta outro
  alvo (nem o círculo de outro alvo pequeno). É puramente geométrico.

Ficam de fora, por não serem observáveis: *user agent control* e *essential*.
Isso é limite declarado, não esquecimento — um alvo pequeno por exigência legal
aparecerá como ofensor e precisa de decisão humana.

Somente stdlib.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# ---------- Value objects ----------


@dataclass(frozen=True)
class Caixa:
    """Retângulo de um elemento na viewport, como o navegador o entrega.

    As coordenadas vêm de `getBoundingClientRect()`, que **já traz a caixa
    transformada**: um alvo com `transform: scale(.5)` chega aqui com metade do
    tamanho, que é o tamanho que o dedo encontra. Medir o layout antes da
    transformação diria o que o CSS pediu, não o que a pessoa toca.
    """

    seletor: str
    x: float
    y: float
    largura: float
    altura: float
    # O alvo está dentro de uma frase (exceção "inline" da 2.5.8). Vem do DOM.
    inline: bool = False
    # Identidade da AÇÃO (href, action, nome acessível). É o que permite decidir
    # a exceção "equivalente": dois controles distintos para a mesma coisa.
    acao: str = ""

    @property
    def centro(self) -> tuple[float, float]:
        return (self.x + self.largura / 2, self.y + self.altura / 2)

    @property
    def menor_lado(self) -> float:
        return min(self.largura, self.altura)


@dataclass(frozen=True)
class AlvoIsento:
    """Alvo abaixo do mínimo que a norma perdoa, com a exceção NOMEADA.

    O nome é obrigatório: "isento" sem motivo é indistinguível de "esquecido", e
    quem audita o laudo precisa poder discordar da exceção aplicada.
    """

    caixa: Caixa
    excecao: str


@dataclass(frozen=True)
class LaudoDeAlvos:
    ofensores: tuple[Caixa, ...] = ()
    alertas: tuple[Caixa, ...] = ()        # atende a norma, abaixo da meta de plataforma
    isentos: tuple[AlvoIsento, ...] = ()
    menor: float | None = None             # None = nenhum alvo medido, nunca 0


# ---------- Distâncias ----------


def _distancia_entre_centros(a: Caixa, b: Caixa) -> float:
    (ax, ay), (bx, by) = a.centro, b.centro
    return math.hypot(ax - bx, ay - by)


def _distancia_do_ponto_ao_retangulo(ponto: tuple[float, float], caixa: Caixa) -> float:
    """Distância euclidiana de um ponto até o retângulo (0 se estiver dentro)."""
    px, py = ponto
    dx = max(caixa.x - px, 0.0, px - (caixa.x + caixa.largura))
    dy = max(caixa.y - py, 0.0, py - (caixa.y + caixa.altura))
    return math.hypot(dx, dy)


# ---------- As três exceções ----------


def _atende(caixa: Caixa, minimo: float) -> bool:
    return caixa.largura >= minimo and caixa.altura >= minimo


def _isento_por_equivalente(alvo: Caixa, outros: list[Caixa], minimo: float) -> bool:
    """Existe outro controle CONFORME para a mesma ação?

    Exige `acao` não vazia: sem identidade da ação, "equivalente" viraria
    "qualquer botão grande na página", que perdoaria tudo.
    """
    if not alvo.acao:
        return False
    return any(o.acao == alvo.acao and o is not alvo and _atende(o, minimo) for o in outros)


def _isento_por_espacamento(alvo: Caixa, outros: list[Caixa], minimo: float) -> bool:
    """Círculo de `minimo` de diâmetro centrado no alvo não toca outro alvo.

    Contra alvo CONFORME, o círculo é testado contra o retângulo dele; contra
    outro alvo pequeno, círculo contra círculo — é o texto da norma, e a
    diferença importa: dois alvos de 16px lado a lado precisam de 24px entre
    centros, não de 12.

    Encostar não é intersectar: distância exatamente igual ao limite é conforme.
    O `<` estrito é o que faz "insuficiente por 1px" reprovar e "no limite"
    passar — e é justamente aí que um check ingênuo erra por arredondamento.
    """
    raio = minimo / 2
    for outro in outros:
        if outro is alvo:
            continue
        if _atende(outro, minimo):
            if _distancia_do_ponto_ao_retangulo(alvo.centro, outro) < raio:
                return False
        elif _distancia_entre_centros(alvo, outro) < minimo:
            return False
    return True


def excecao_de(alvo: Caixa, outros: list[Caixa], minimo: float) -> str:
    """Nome da exceção da 2.5.8 que perdoa este alvo, ou "" se nenhuma perdoa.

    Ordem deliberada: a mais barata de explicar primeiro. Quem lê o laudo
    entende "está dentro de uma frase" mais rápido que "o círculo de 24px não
    intersecta nenhum vizinho".
    """
    if alvo.inline:
        return "inline"
    if _isento_por_equivalente(alvo, outros, minimo):
        return "equivalente"
    if _isento_por_espacamento(alvo, outros, minimo):
        return "espacamento"
    return ""


def classificar_alvos(caixas: list[Caixa], *, minimo: float, meta: float) -> LaudoDeAlvos:
    """Classifica cada alvo em ofensor, alerta ou isento (com a exceção nomeada).

    `alertas` são alvos que ATENDEM à norma (>= `minimo`) e ficam abaixo da meta
    de plataforma (`meta`, 44px). Alerta e não achado, porque 44 é recomendação
    de fabricante, não critério da WCAG — cobrar norma que não existe desgasta a
    bateria tanto quanto deixar de cobrar a que existe.
    """
    ofensores, alertas, isentos = [], [], []
    for caixa in caixas:
        if _atende(caixa, minimo):
            if caixa.menor_lado < meta:
                alertas.append(caixa)
            continue
        excecao = excecao_de(caixa, caixas, minimo)
        (isentos.append(AlvoIsento(caixa, excecao)) if excecao else ofensores.append(caixa))
    return LaudoDeAlvos(
        ofensores=tuple(ofensores), alertas=tuple(alertas), isentos=tuple(isentos),
        # `None` quando não havia alvo: ausência de medida não é alvo de 0px.
        menor=min((c.menor_lado for c in caixas), default=None),
    )


# ---------- Zoom: o que sumiu entre dois inventários ----------


@dataclass(frozen=True)
class Perdas:
    marcos: tuple[str, ...] = ()
    textos: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.marcos) + len(self.textos)


def perdidos_entre(normal: dict, ampliado: dict) -> Perdas:
    """O que existia no inventário normal e sumiu no ampliado (WCAG 1.4.4).

    Compara CONJUNTOS de texto normalizado, nunca posições: a 200% tudo se move,
    e comparar coordenadas acusaria a ampliação em si como perda. O que a norma
    proíbe é conteúdo ou função deixar de estar disponível.
    """
    marcos = tuple(sorted(set(normal.get("marcos") or ()) - set(ampliado.get("marcos") or ())))
    textos = tuple(sorted(set(normal.get("textos") or ()) - set(ampliado.get("textos") or ())))
    return Perdas(marcos=marcos, textos=textos)


# ---------- Sobreposição entre interativos (GUI-RESP-03) ----------


@dataclass(frozen=True)
class Interativo:
    """Um controle clicável e os ancestrais dele que TAMBÉM são controles.

    Os ancestrais vêm por índice porque a exclusão que interessa é estrutural,
    não geométrica: um `<a>` dentro de um `<nav>` clicável cobre 100% de si
    mesmo dentro do pai, e chamar isso de sobreposição acusaria de defeito o
    aninhamento normal de qualquer menu.
    """

    caixa: Caixa
    ancestrais: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Sobreposicao:
    """Dois controles que dividem área — com a fração, que é o que decide."""

    a: Caixa
    b: Caixa
    fracao: float

    def __str__(self) -> str:
        return (f"{self.a.seletor} × {self.b.seletor} — {self.fracao * 100:.0f}% "
                f"da menor caixa ({self.a.largura:.0f}x{self.a.altura:.0f} e "
                f"{self.b.largura:.0f}x{self.b.altura:.0f}px)")


def area_de_intersecao(a: Caixa, b: Caixa) -> float:
    """Área do retângulo comum. Zero quando só se encostam."""
    largura = min(a.x + a.largura, b.x + b.largura) - max(a.x, b.x)
    altura = min(a.y + a.altura, b.y + b.altura) - max(a.y, b.y)
    return max(0.0, largura) * max(0.0, altura)


def fracao_da_menor(a: Caixa, b: Caixa) -> float:
    """Interseção como fração da MENOR das duas caixas.

    Da menor, e não da soma nem da maior: um botão pequeno inteiramente coberto
    por um painel grande está 100% inacessível, e dividir pela área do painel
    daria uma fração minúscula — a métrica diria "quase nada" sobre um controle
    que ninguém consegue tocar.
    """
    menor = min(a.largura * a.altura, b.largura * b.altura)
    if menor <= 0:
        return 0.0
    return area_de_intersecao(a, b) / menor


def sobreposicoes(interativos, *, limite: float) -> tuple[Sobreposicao, ...]:
    """Pares que dividem mais que `limite` da menor caixa, do pior para o melhor.

    O comparador é `>`, não `>=`: na fração exata do limite o par ainda está
    dentro do que se admite. Mesma disciplina de borda do 25% da cobertura de
    foco (OS-43) e dos 50ms do TBT (OS-46) — a borda é decisão, e decisão tem
    teste.
    """
    itens = list(interativos)
    achados = []
    for i, um in enumerate(itens):
        for j in range(i + 1, len(itens)):
            outro = itens[j]
            if j in um.ancestrais or i in outro.ancestrais:
                continue
            fracao = fracao_da_menor(um.caixa, outro.caixa)
            if fracao > limite:
                achados.append(Sobreposicao(um.caixa, outro.caixa, fracao))
    return tuple(sorted(achados, key=lambda s: -s.fracao))


def interativos_de(brutos) -> tuple[Interativo, ...]:
    """Traduz o que `JS_INTERATIVOS` devolveu."""
    return tuple(
        Interativo(
            caixa=Caixa(seletor=str(b.get("seletor") or "?"),
                        x=float(b.get("x") or 0.0), y=float(b.get("y") or 0.0),
                        largura=float(b.get("largura") or 0.0),
                        altura=float(b.get("altura") or 0.0)),
            ancestrais=frozenset(int(i) for i in (b.get("ancestrais") or ())),
        )
        for b in (brutos or ())
    )


def resumo_de_sobreposicoes(achados, teto: int = 10) -> str:
    linhas = [f"  {s}" for s in list(achados)[:teto]]
    if len(list(achados)) > teto:
        linhas.append(f"  … e mais {len(list(achados)) - teto}")
    return "\n".join(linhas)


# ---------- Resumos para a mensagem do assert ----------


def resumo_de_caixas(caixas, teto: int = 10) -> str:
    """Seletor + caixa medida, uma por linha. É a EVIDÊNCIA desta dimensão.

    Não é consolo por não haver screenshot: seletor e número são o que vai para
    o ticket e o que o desenvolvedor usa para achar o elemento. A imagem
    ajudaria a ver; ela não ajudaria a corrigir.
    """
    linhas = [f"  {c.seletor} — {c.largura:.0f}x{c.altura:.0f}px" for c in caixas[:teto]]
    if len(caixas) > teto:
        linhas.append(f"  … e mais {len(caixas) - teto}")
    return "\n".join(linhas)


def resumo_de_isentos(isentos, teto: int = 5) -> str:
    """Isentos com a exceção nomeada — para o laudo poder ser contestado."""
    linhas = [f"  {i.caixa.seletor} — isento por {i.excecao}" for i in isentos[:teto]]
    if len(isentos) > teto:
        linhas.append(f"  … e mais {len(isentos) - teto}")
    return "\n".join(linhas)


# ---------- Coletores (JavaScript executado na página) ----------

# Um seletor curto e ESTÁVEL por elemento. `id` quando existe; senão, caminho de
# no máximo três níveis com `nth-of-type`. Não é para ser bonito — é para o
# desenvolvedor colar no DevTools e achar o elemento.
#
# É um trecho a ser COLADO DENTRO da função, e não uma declaração ao lado dela:
# `page.evaluate` avalia uma EXPRESSÃO. Uma declaração seguida de uma arrow
# function é dois enunciados, e o navegador recusa com "Malformed arrow function
# parameter list" — erro cujo texto não aponta para a causa.
_SELETOR = """
  const seletorDe = (el) => {
    if (el.id) { return el.tagName.toLowerCase() + '#' + el.id; }
    const partes = [];
    let atual = el;
    for (let i = 0; i < 3 && atual && atual.tagName; i++) {
      let parte = atual.tagName.toLowerCase();
      const classe = (atual.className || '').toString().trim().split(/\\s+/)[0];
      if (classe) { parte += '.' + classe; }
      const irmaos = atual.parentElement
        ? [...atual.parentElement.children].filter(c => c.tagName === atual.tagName) : [];
      if (irmaos.length > 1) { parte += ':nth-of-type(' + (irmaos.indexOf(atual) + 1) + ')'; }
      partes.unshift(parte);
      atual = atual.parentElement;
    }
    return partes.join(' > ');
  };
"""

# Interativos VISÍVEIS. Coleta o elemento clicável, nunca o ícone dentro dele:
# a área de toque costuma vir do padding do ancestral, e medir o `<svg>` acusaria
# um alvo confortável de pequeno.
JS_ALVOS_DE_TOQUE = """
() => {
""" + _SELETOR + """
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, ' +
              '[role=button], [role=link], [tabindex]:not([tabindex="-1"])';
  const visivel = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || el.closest('[aria-hidden=true]')) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  // "inline" da 2.5.8: o alvo divide a linha com texto que não é dele, então o
  // tamanho vem da entrelinha, não de uma escolha de quem desenhou.
  const dentroDeFrase = (el) => {
    const pai = el.parentElement;
    if (!pai) { return false; }
    const textoDoPai = (pai.textContent || '').trim();
    const textoDoAlvo = (el.textContent || '').trim();
    return textoDoPai.length > textoDoAlvo.length + 1 && getComputedStyle(el).display === 'inline';
  };
  const acaoDe = (el) => el.getAttribute('href') || el.getAttribute('formaction') ||
                         (el.form && el.form.getAttribute('action')) ||
                         el.getAttribute('aria-label') || (el.textContent || '').trim();
  return [...document.querySelectorAll(SEL)].filter(visivel).map(el => {
    const r = el.getBoundingClientRect();
    return {seletor: seletorDe(el), x: r.x, y: r.y, largura: r.width, altura: r.height,
            inline: dentroDeFrase(el), acao: acaoDe(el)};
  });
}
"""

# Interativos visíveis + a ancestralidade ENTRE eles (GUI-RESP-03).
#
# A ancestralidade vai por índice, calculada aqui e não no Python, porque só o
# navegador tem a árvore: reconstruí-la a partir do seletor de texto seria
# adivinhar. `contains` responde a pergunta exata — "este controle está DENTRO
# daquele?" — e é o que exclui o link dentro do nav do veredito.
JS_INTERATIVOS = """
() => {
""" + _SELETOR + """
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, ' +
              '[role=button], [role=link], [tabindex]:not([tabindex="-1"])';
  const visivel = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || el.closest('[aria-hidden=true]')) {
      return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const nos = [...document.querySelectorAll(SEL)].filter(visivel);
  return nos.map((el, i) => {
    const r = el.getBoundingClientRect();
    const ancestrais = [];
    nos.forEach((outro, j) => {
      if (j !== i && outro.contains(el)) { ancestrais.push(j); }
    });
    return {seletor: seletorDe(el), x: r.x, y: r.y, largura: r.width, altura: r.height,
            ancestrais: ancestrais};
  });
}
"""

# Rolagem horizontal do documento e quem extravasa a viewport (WCAG 1.4.10).
JS_OVERFLOW = """
() => {
""" + _SELETOR + """
  const raiz = document.scrollingElement || document.documentElement;
  const limite = raiz.clientWidth;
  const extravasantes = [...document.querySelectorAll('body *')]
    .filter(el => {
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden') { return false; }
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right > limite + 1;
    })
    // Só o ancestral mais externo de cada cadeia: um pai largo faz todo filho
    // "extravasar", e listar a cadeia inteira esconde a causa no meio do ruído.
    .filter((el, _i, todos) => !todos.some(o => o !== el && o.contains(el)))
    .map(el => {
      const r = el.getBoundingClientRect();
      return {seletor: seletorDe(el), x: r.x, y: r.y, largura: r.width, altura: r.height};
    });
  return {overflow: Math.max(0, raiz.scrollWidth - limite), extravasantes: extravasantes};
}
"""

# Inventário do que a página oferece — comparado antes e depois do zoom (1.4.4).
JS_INVENTARIO = """
() => {
  const norm = t => (t || '').replace(/\\s+/g, ' ').trim();
  const principal = document.querySelector('main') || document.body;
  const marcos = [...document.querySelectorAll(
      'main, nav, header, footer, h1, h2, button, a[href], input, select, textarea')]
    .filter(el => {
      const s = getComputedStyle(el);
      return s.display !== 'none' && s.visibility !== 'hidden';
    })
    .map(el => el.tagName.toLowerCase() + ':' + norm(el.getAttribute('aria-label') ||
         el.textContent).slice(0, 40))
    .filter(m => m.length > 2);
  const textos = [...principal.querySelectorAll('p, li, td, th, dd, dt, figcaption')]
    .filter(el => {
      const s = getComputedStyle(el);
      // `overflow: hidden` com conteúdo maior que a caixa é conteúdo CORTADO —
      // ele está no DOM e não está disponível para quem lê. É perda.
      if (s.display === 'none' || s.visibility === 'hidden') { return false; }
      if (s.overflow === 'hidden' && el.scrollHeight > el.clientHeight + 1) { return false; }
      return true;
    })
    .map(el => norm(el.textContent).slice(0, 80))
    .filter(t => t.length > 3);
  return {marcos: [...new Set(marcos)], textos: [...new Set(textos)]};
}
"""
