"""A caminhada de foco e os três vereditos que ela sustenta.

Uma caminhada, três critérios — **2.4.7** (foco visível), **2.4.3** (ordem de
tabulação) e **2.4.11** (foco não obscurecido, novo na 2.2). A economia é a
mesma de `home_response` nas dimensões HTTP: percorrer a página com Tab é caro e
mexe no estado do navegador; fazê-lo três vezes seria pagar três vezes por uma
observação só, e ainda abriria a chance de as três caminhadas discordarem entre
si num alvo com conteúdo dinâmico.

`caminhar` recebe as ações por PARÂMETRO (`pressionar_tab`, `ler_foco`), como
`webqa/navegacao.py::percorrer` já faz com `abrir`. É o que permite provar a
detecção de armadilha sobre um ciclo fabricado, sem navegador e sem esperar 200
Tabs de verdade.

Três decisões que valem mais que o código:

* **teto de Tabs, nunca laço aberto.** Armadilha de foco tem de virar falha
  EXPLICADA, não travamento nem timeout. Um teste que pendura é um teste que
  alguém desliga;
* **inversão é geométrica, não do DOM.** `order` do flexbox e `grid-area`
  desacoplam a ordem do DOM da ordem visual legitimamente — e é justamente esse
  descolamento que a 2.4.3 existe para pegar. Comparar com o DOM acusaria todo
  layout moderno e perderia a violação real;
* **subir e ir para a DIREITA não é inversão.** É mudança de coluna, e é a
  ordem de leitura esperada num layout em colunas. Sem essa regra, toda grade
  de duas colunas apareceria como violação.

Somente stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from webqa.geometria import Caixa

# Teto de Tabs. Alto o bastante para uma página densa, baixo o bastante para o
# check terminar em segundos quando o foco está preso.
TETO_DE_TABS = 200

# Abaixo disto, um ciclo que não escapa é foco PRESO. Acima, é página comprida:
# 200 elementos focáveis distintos existem em documentação e tabelão. A distinção
# vai na mensagem, porque as duas exigem ações opostas de quem lê o laudo.
_CICLO_CURTO = 12

# Quanto da caixa focada pode estar coberto e ainda ser conforme. A 2.4.11
# (Minimum) proíbe o foco INTEIRAMENTE oculto; adotamos um quarto como limite
# operacional, e ele é `>` estrito — cobertura de exatamente 25% passa.
COBERTURA_MAXIMA = 0.25

# Propriedades que carregam indicador de foco. Nenhuma isolada basta: há tema
# que marca foco só por `background-color`, e há reset que zera `outline` e
# devolve o sinal por `box-shadow`.
PROPRIEDADES_DE_FOCO = (
    "outline-style", "outline-width", "outline-color",
    "box-shadow", "border-color", "border-width",
    "background-color", "text-decoration-line", "color",
)


@dataclass(frozen=True)
class Parada:
    """Um elemento com foco, e tudo que os três critérios precisam saber dele."""

    seletor: str
    caixa: Caixa
    estilo_com_foco: dict = field(default_factory=dict)
    estilo_sem_foco: dict = field(default_factory=dict)
    # Fração da caixa coberta por outro elemento (2.4.11).
    fracao_coberta: float = 0.0
    # Quem cobre. Sem este nome, quem lê o achado não sabe por onde começar —
    # "o foco está coberto" não diz se o culpado é o cabeçalho fixo, o banner de
    # consentimento ou o chat de suporte.
    cobridor: str = ""
    em_iframe: bool = False

    @property
    def estilo_muda_com_foco(self) -> bool:
        """Alguma propriedade de indicação difere entre focado e não focado."""
        return any(self.estilo_com_foco.get(p) != self.estilo_sem_foco.get(p)
                   for p in PROPRIEDADES_DE_FOCO)

    @property
    def obscurecida(self) -> bool:
        return self.fracao_coberta > COBERTURA_MAXIMA


@dataclass(frozen=True)
class Caminhada:
    paradas: tuple[Parada, ...] = ()
    teto_atingido: bool = False
    # Seletores que se repetem no fim da caminhada — o ciclo em que o foco ficou.
    ciclo: tuple[str, ...] = ()
    # Focáveis que a caminhada NUNCA alcançou. É o que separa fim de ordem de
    # armadilha — ver `armadilha`. Vazio quando não houve inventário.
    inalcancados: tuple[str, ...] = ()
    # Houve inventário? Sem ele não dá para afirmar cobertura, e o lado seguro
    # é não acusar armadilha (acusar errado é o defeito que isto conserta).
    inventario_conhecido: bool = False
    # Veredito da sonda Shift+Tab no ponto de estagnação: "armadilha",
    # "fim_de_ordem" ou "" (não sondado). Evidência COMPORTAMENTAL, e por isso
    # tem prioridade sobre a cobertura — ver `armadilha`.
    sonda: str = ""

    @property
    def armadilha(self) -> bool:
        """Foco preso — e o discriminador é COBERTURA, não contagem.

        Duas situações produzem a mesma assinatura (o teto atingido repetindo
        poucos elementos), e confundi-las custou três `error` no Firefox:

        * **armadilha** — o foco gira entre poucos elementos E ainda havia
          focáveis por visitar. Quem navega por teclado não alcança o resto;
        * **fim de ordem** — o foco parou no último e não havia mais nada por
          visitar. Não é defeito do alvo: é o Chromium que dá a volta na ordem
          de tabulação e o Firefox que não. Medido no runner e reproduzido:
          o Firefox percorre os 15 focáveis na mesma ordem, congela no último
          (o foco vai para a interface do navegador) e `document.activeElement`
          não muda mais até o teto.

        Contagem sozinha não separa os dois: a armadilha plantada do fixture
        (`onblur="this.focus()"`) também repete UM elemento.

        **A cobertura sozinha não basta**, e a validação mostrou onde: quando a
        armadilha está no ÚLTIMO focável — que é o caso da plantada em
        `/gui/estados` —, não sobra ninguém por visitar e os dois casos ficam
        idênticos aos olhos da cobertura. Daí a sonda `Shift+Tab`, que é
        evidência comportamental e por isso tem prioridade:

        * **fim de ordem** — o foco tinha saído do documento; Shift+Tab o traz
          de volta ao elemento ANTERIOR (ou a lugar nenhum);
        * **armadilha** — o `onblur` cancela qualquer saída, e Shift+Tab devolve
          o foco ao MESMO elemento.

        Cobertura pega a armadilha no meio da página; a sonda pega a do fim.

        Sem sonda e sem inventário não se afirma armadilha. Coletor que falhou é
        ausência de medida, e ausência de medida não vira acusação.
        """
        if not (self.teto_atingido and 0 < len(self.ciclo) <= _CICLO_CURTO):
            return False
        if self.sonda:
            return self.sonda == "armadilha"
        if not self.inventario_conhecido:
            return False
        return bool(self.inalcancados)

    @property
    def fim_de_ordem(self) -> bool:
        """Estagnou tendo visitado tudo — término NORMAL, e os checks rodam.

        Existe como propriedade própria para o laudo poder dizer o que houve.
        Tratar isto como skip trocaria um falso positivo por um falso silêncio:
        os três critérios de foco continuariam sem medir nada naquela engine.
        """
        if not (self.teto_atingido and bool(self.ciclo)):
            return False
        if self.sonda:
            return self.sonda == "fim_de_ordem"
        return self.inventario_conhecido and not self.inalcancados

    @property
    def em_iframe(self) -> tuple[Parada, ...]:
        """Paradas dentro de iframe: saem dos vereditos e vão para o laudo.

        Estilo computado e `elementFromPoint` do documento de fora não alcançam o
        conteúdo de um iframe de terceiro. Medir assim mesmo produziria "sem
        indicador de foco" para todo widget embutido — falso positivo garantido.
        Declarar é honesto; ignorar em silêncio seria fingir cobertura.
        """
        return tuple(p for p in self.paradas if p.em_iframe)

    @property
    def avaliaveis(self) -> tuple[Parada, ...]:
        return tuple(p for p in self.paradas if not p.em_iframe)


def caminhar(pressionar_tab, ler_foco, teto: int = TETO_DE_TABS,
             focaveis=None, voltar_tab=None) -> Caminhada:
    """Pressiona Tab até voltar ao início, o foco sair, ou o teto estourar.

    `ler_foco()` devolve uma `Parada` ou `None` quando o foco deixou o documento
    (barra de endereços do navegador, fim natural). Ambos são término normal.

    `voltar_tab` pressiona Shift+Tab e é usado UMA vez, só no ponto de
    estagnação, para separar armadilha de fim de ordem por comportamento. Também
    injetado — esta função não abre navegador.

    `focaveis` é o inventário de seletores que o navegador diz serem focáveis —
    injetado, como as ações, para que esta função siga pura e testável sem subir
    navegador. É ele que permite responder "sobrou alguém por visitar?", que é a
    única pergunta que separa armadilha de fim de ordem. Ausente, a caminhada
    não afirma armadilha.
    """
    paradas: list[Parada] = []
    for _ in range(teto):
        pressionar_tab()
        parada = ler_foco()
        if parada is None:
            break
        if paradas and parada.seletor == paradas[0].seletor:
            break                      # voltou ao primeiro: ciclo completo, normal
        paradas.append(parada)
    else:
        ciclo = _ciclo_final(paradas)
        return Caminhada(paradas=tuple(paradas), teto_atingido=True, ciclo=ciclo,
                         sonda=_sondar_retorno(voltar_tab, ler_foco, paradas),
                         **_cobertura(paradas, focaveis))
    return Caminhada(paradas=tuple(paradas), **_cobertura(paradas, focaveis))


def _sondar_retorno(voltar_tab, ler_foco, paradas: list[Parada]) -> str:
    """Shift+Tab no ponto de estagnação. "" quando não há como sondar.

    Um toque só, e só aqui: a pergunta é se o elemento SOLTA o foco. Se soltar,
    a caminhada tinha chegado ao fim da ordem e a engine é que não dá a volta;
    se não soltar, alguma coisa o está prendendo.
    """
    if voltar_tab is None or not paradas:
        return ""
    preso = paradas[-1].seletor
    try:
        voltar_tab()
        depois = ler_foco()
    except Exception:
        return ""              # instrumentação não decide veredito
    if depois is None:
        return "fim_de_ordem"  # o foco saiu do documento: nada o prendia
    return "armadilha" if depois.seletor == preso else "fim_de_ordem"


def _cobertura(paradas: list[Parada], focaveis) -> dict:
    """Quem o inventário prometia e a caminhada não alcançou."""
    if focaveis is None:
        return {"inventario_conhecido": False, "inalcancados": ()}
    visitados = {p.seletor for p in paradas}
    faltando = tuple(s for s in dict.fromkeys(focaveis) if s not in visitados)
    return {"inventario_conhecido": True, "inalcancados": faltando}


def _ciclo_final(paradas: list[Parada], janela: int = 20) -> tuple[str, ...]:
    """Seletores distintos no fim da caminhada, na ordem em que aparecem."""
    vistos: dict[str, None] = {}
    for parada in paradas[-janela:]:
        vistos.setdefault(parada.seletor, None)
    return tuple(vistos)


# ---------- 2.4.3: ordem de tabulação × ordem visual ----------


def _mesma_faixa(a: Caixa, b: Caixa, tolerancia: float) -> bool:
    return abs(a.y - b.y) <= tolerancia


def _volta_atras_na_linha(anterior: Caixa, seguinte: Caixa, direcao: str) -> bool:
    """Na mesma faixa horizontal, o foco andou para trás na direção da leitura."""
    if direcao == "rtl":
        return seguinte.x >= anterior.x + anterior.largura
    return seguinte.x + seguinte.largura <= anterior.x


def _sobe_sem_mudar_de_coluna(anterior: Caixa, seguinte: Caixa, direcao: str,
                              tolerancia: float) -> bool:
    """Subiu na página SEM avançar na direção da leitura.

    Subir e avançar (direita em LTR) é mudança de coluna — a ordem de leitura
    esperada num layout em colunas, e o falso positivo que derruba um check
    ingênuo em qualquer grade de duas colunas.
    """
    if seguinte.y >= anterior.y - tolerancia:
        return False
    avancou = seguinte.x < anterior.x if direcao == "rtl" else seguinte.x > anterior.x
    return not avancou


def inversoes_de_leitura(caixas: list[Caixa], *, direcao: str = "ltr",
                         tolerancia: float = 24.0) -> list[tuple[int, int]]:
    """Índices dos pares consecutivos em que a tabulação contraria a leitura.

    Heurística, e declarada como tal: a geometria não conhece a intenção do
    layout. É por isso que o limiar do check é folgado na Fase 1 — reprovar por
    decisão legítima de layout desgasta a bateria mais do que deixar passar dois
    saltos.
    """
    inversoes = []
    for indice, (anterior, seguinte) in enumerate(zip(caixas, caixas[1:], strict=False)):
        if _mesma_faixa(anterior, seguinte, tolerancia):
            if _volta_atras_na_linha(anterior, seguinte, direcao):
                inversoes.append((indice, indice + 1))
        elif _sobe_sem_mudar_de_coluna(anterior, seguinte, direcao, tolerancia):
            inversoes.append((indice, indice + 1))
    return inversoes


# ---------- 2.4.11: quanto da caixa focada está coberto ----------


def fracao_coberta_de(amostras) -> float:
    """Fração dos pontos amostrados em que outro elemento está por cima.

    Amostragem em grade 4×4, e não 3×3: com nove pontos o limiar de 25% não é
    representável (1/9 = 11%, 2/9 = 22%, 3/9 = 33%), e um limiar que a
    amostragem não consegue expressar é um limiar que nunca foi testado na
    borda. Com dezesseis, 4/16 é exatamente 25%.
    """
    amostras = list(amostras)
    if not amostras:
        return 0.0
    return sum(1 for coberto in amostras if coberto) / len(amostras)


# ---------- Resumos para a mensagem do assert ----------


def resumo_de_paradas(paradas, teto: int = 10) -> str:
    linhas = [f"  {p.seletor}" for p in paradas[:teto]]
    if len(paradas) > teto:
        linhas.append(f"  … e mais {len(paradas) - teto}")
    return "\n".join(linhas)


def resumo_de_cobertura(paradas, teto: int = 10) -> str:
    """Nomeia QUEM cobre — sem isso o achado não diz por onde começar."""
    linhas = [f"  {p.seletor} — {p.fracao_coberta:.0%} coberto por {p.cobridor or '?'}"
              for p in paradas[:teto]]
    if len(paradas) > teto:
        linhas.append(f"  … e mais {len(paradas) - teto}")
    return "\n".join(linhas)


def resumo_de_inversoes(paradas, inversoes, teto: int = 5) -> str:
    linhas = []
    for anterior, seguinte in inversoes[:teto]:
        linhas.append(f"  {paradas[anterior].seletor} → {paradas[seguinte].seletor}")
    if len(inversoes) > teto:
        linhas.append(f"  … e mais {len(inversoes) - teto}")
    return "\n".join(linhas)


# ---------- Coletor (JavaScript executado na página) ----------

# Lê TUDO de uma parada numa única avaliação: seletor, caixa, estilo com e sem
# foco, cobertura e origem. Uma chamada por Tab, e não cinco — cada ida ao
# navegador é um instante diferente, e cinco instantes descreveriam cinco
# páginas quando há conteúdo dinâmico.
JS_FOCO_ATUAL = """
() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) { return null; }
  const seletorDe = (n) => {
    if (!n || !n.tagName) { return '?'; }
    if (n.id) { return n.tagName.toLowerCase() + '#' + n.id; }
    const partes = [];
    let atual = n;
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
  const PROPS = ['outline-style', 'outline-width', 'outline-color', 'box-shadow',
                 'border-color', 'border-width', 'background-color',
                 'text-decoration-line', 'color'];
  const lerEstilo = (n) => {
    const s = getComputedStyle(n);
    const fora = {};
    for (const p of PROPS) { fora[p] = s.getPropertyValue(p); }
    return fora;
  };
  const comFoco = lerEstilo(el);
  // O estado SEM foco vem de um clone fora da árvore de foco. Tirar o foco do
  // elemento para medir moveria a caminhada — o instrumento mudaria o que ele
  // está medindo.
  const clone = el.cloneNode(false);
  clone.removeAttribute('id');
  clone.style.position = 'absolute';
  clone.style.left = '-99999px';
  (el.parentElement || document.body).appendChild(clone);
  const semFoco = lerEstilo(clone);
  clone.remove();

  const r = el.getBoundingClientRect();
  // Grade 4x4: com 3x3 o limiar de 25% não é representável e a borda nunca
  // seria exercida.
  const amostras = [];
  let cobridor = '';
  for (let i = 1; i <= 4; i++) {
    for (let j = 1; j <= 4; j++) {
      const px = r.left + (r.width * i) / 5;
      const py = r.top + (r.height * j) / 5;
      const acima = document.elementFromPoint(px, py);
      const coberto = !!acima && acima !== el && !el.contains(acima) && !acima.contains(el);
      if (coberto && !cobridor) { cobridor = seletorDe(acima); }
      amostras.push(coberto);
    }
  }
  return {seletor: seletorDe(el), x: r.x, y: r.y, largura: r.width, altura: r.height,
          estilo_com_foco: comFoco, estilo_sem_foco: semFoco,
          amostras: amostras, cobridor: cobridor,
          em_iframe: el.tagName.toLowerCase() === 'iframe'};
}
"""


def parada_de(bruto: dict) -> Parada:
    """Converte o retorno do coletor numa `Parada`. Puro."""
    return Parada(
        seletor=bruto["seletor"],
        caixa=Caixa(seletor=bruto["seletor"], x=bruto["x"], y=bruto["y"],
                    largura=bruto["largura"], altura=bruto["altura"]),
        estilo_com_foco=bruto.get("estilo_com_foco") or {},
        estilo_sem_foco=bruto.get("estilo_sem_foco") or {},
        fracao_coberta=fracao_coberta_de(bruto.get("amostras") or []),
        cobridor=bruto.get("cobridor") or "",
        em_iframe=bool(bruto.get("em_iframe")),
    )
