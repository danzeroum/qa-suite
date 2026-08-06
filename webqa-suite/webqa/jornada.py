"""Jornada de usabilidade: a pessoa chega onde veio? (GUI-JORN-01/02, OS-51)

A aceitação da casa é qualitativa — o cenário passa ou não passa. Sem número não
há tendência, e sem tendência não há regressão detectável: um site que hoje leva
dois cliques até a política e amanhã leva cinco continua "passando" nos dois dias.

Três medidas, e a diferença entre elas é o desenho inteiro:

* **TSR** (*task success rate*) — chegou ou não chegou. Binário e determinístico;
* **cliques excedentes** — quantos cliques ALÉM do menor caminho que a própria
  aplicação oferece. É a medida que interessa, e o motivo está abaixo;
* **ToT** (*time on task*) — tempo até concluir. É TEMPO, logo é ambiente, e
  segue a navalha da casa: só reprova sob `WEBQA_ORIGEM=vps`.

**Por que o percurso não é o caminho ótimo.** O robô imita o que a pessoa faz —
**ler os rótulos** e seguir o que parece levar à tarefa. Fazê-lo andar pelo
caminho ótimo daria excedente zero sempre, e mediria a topologia do site em vez
da sua legibilidade. O ótimo é a **régua**, não o percurso: a diferença entre o
que os rótulos induzem e o que a estrutura permite **é o preço do rótulo ruim**,
e é exatamente o que uma sessão com usuário mede quando a pessoa vai e volta.

O limite disso está declarado e não é pequeno: afinidade de rótulo é uma
heurística de palavras, e uma pessoa usa contexto, posição na página, memória e
convenção de mercado. O que se mede aqui é um **limite inferior** da facilidade
de encontrar — encontra o rótulo grosseiramente errado, não descreve a cauda.
Chamar isso de "usabilidade medida" prometeria uma sessão a partir de um crawl.

Núcleo PURO: recebe grafo e rótulos, decide, e não sabe o que é um navegador.
Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

import unicodedata
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PERFIS_PADRAO = RAIZ / "data" / "gui-perfis.yaml"

# Palavras curtas demais para discriminar rótulo ("de", "a", "e"). Não é lista de
# stopwords de linguística: é o mínimo para que "fale com a loja" não case com
# qualquer link que contenha "a".
TAMANHO_MINIMO_DE_PALAVRA = 3


@dataclass(frozen=True)
class Tarefa:
    """Uma tarefa de jornada, declarada por quem conhece o alvo.

    `procura` são as palavras que a PESSOA levaria na cabeça ao procurar — é o
    que o rótulo precisa evocar. `marco` é como se reconhece que chegou: o texto
    que a pessoa leria na página de destino para ter certeza.
    """

    nome: str
    procura: tuple[str, ...]
    marco: str
    cliques_extras_max: int
    tot_ms: float

    def __str__(self) -> str:
        return f"{self.nome!r} (procura por {', '.join(self.procura)}; chega em {self.marco!r})"


def carregar_tarefas(caminho: str | Path | None = None) -> dict[str, Tarefa]:
    """Lê o bloco `jornadas:` de `data/gui-perfis.yaml` → {nome: Tarefa}."""
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    tarefas: dict[str, Tarefa] = {}
    for bruto in (dados.get("jornadas") or []):
        if not isinstance(bruto, Mapping) or "nome" not in bruto:
            raise ValueError(f"tarefa de jornada sem 'nome' em gui-perfis.yaml: {bruto!r}")
        nome = str(bruto["nome"])
        faltando = [c for c in ("procura", "marco", "cliques_extras_max", "tot_ms")
                    if c not in bruto]
        if faltando:
            raise ValueError(f"tarefa de jornada {nome!r} sem {faltando} em gui-perfis.yaml")
        tarefas[nome] = Tarefa(
            nome=nome,
            procura=tuple(str(p) for p in bruto["procura"]),
            marco=str(bruto["marco"]),
            cliques_extras_max=int(bruto["cliques_extras_max"]),
            tot_ms=float(bruto["tot_ms"]),
        )
    if not tarefas:
        raise ValueError("gui-perfis.yaml não declara nenhuma jornada")
    return tarefas


def tarefa_de(nome: str, tarefas: Mapping[str, Tarefa]) -> Tarefa:
    """A tarefa pedida, ou ERRO nomeando as válidas.

    Fail-closed pela mesma razão dos viewports e dos perfis de rede: um cenário
    que citasse tarefa inexistente não pode degenerar em "não mediu e passou".
    """
    if nome not in tarefas:
        raise ValueError(
            f"tarefa de jornada desconhecida: {nome!r}. Válidas: {', '.join(tarefas)}.")
    return tarefas[nome]


# ---------- normalização de texto ----------

def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def palavras(texto: str) -> frozenset[str]:
    """Palavras normalizadas de um texto: sem acento, sem caixa, sem as curtas."""
    limpo = _sem_acento(texto or "").lower()
    cru = "".join(c if c.isalnum() else " " for c in limpo).split()
    return frozenset(p for p in cru if len(p) >= TAMANHO_MINIMO_DE_PALAVRA)


def afinidade(rotulo: str, procura: tuple[str, ...]) -> float:
    """Quanto este rótulo se parece com o que a pessoa procura, em [0, 1].

    Fração das palavras da PROCURA que aparecem no rótulo — e não o contrário:
    um rótulo longo que contenha o que se procura ("Leia nossa política de
    privacidade e os termos") deve pontuar alto, enquanto um rótulo curto que
    não contenha nada da procura não deve pontuar por ser curto.
    """
    alvo = frozenset().union(*(palavras(p) for p in procura)) if procura else frozenset()
    if not alvo:
        return 0.0
    return len(alvo & palavras(rotulo)) / len(alvo)


# ---------- o grafo ----------

def arestas_com_rotulo(html: str, url: str, host: str) -> tuple[tuple[str, str], ...]:
    """`((destino, rótulo), ...)` desta página.

    As ARESTAS vêm de `webqa/navegacao.py::links_oferecidos` — a autoridade da
    casa sobre o que conta como link de mesmo host. O rótulo é enriquecido por
    uma leitura própria e casado POR URL; nenhuma aresta nasce aqui, então as
    duas leituras não podem divergir sobre o que é link.
    """
    from bs4 import BeautifulSoup

    from webqa.navegacao import links_oferecidos

    sopa = BeautifulSoup(html or "", "lxml")
    rotulos: dict[str, str] = {}
    for etiqueta in sopa.find_all(["a", "area"], href=True):
        texto = etiqueta.get_text(" ", strip=True) or (etiqueta.get("aria-label") or "")
        if texto:
            rotulos.setdefault((etiqueta["href"] or "").strip().split("#")[0], texto)
    arestas = []
    for destino, _ in links_oferecidos(html or "", url, host):
        rotulo = next((t for h, t in rotulos.items() if h and destino.endswith(h)), "")
        arestas.append((destino, rotulo))
    return tuple(arestas)


def reconhece_destino(marco: str, html: str) -> bool:
    """Chegou? A pessoa reconhece pelo TÍTULO e pelos CABEÇALHOS, e o robô também.

    Comparar a URL seria mais fácil e mediria outra coisa: endereço bonito não é
    a página certa, e endereço feio não é a errada.

    **Título e cabeçalhos, e não o texto inteiro — a medição obrigou.** A
    primeira versão varria todo o texto visível, e a home do alvo fabricado
    passou a ser reconhecida como a própria página de destino, porque ela CITA o
    destino num rótulo de link ("Politica de Privacidade"). O resultado era um
    TSR=1 com ZERO cliques: a pessoa "chegava" sem sair do lugar, e o cenário
    passava anunciando sucesso numa jornada que nunca aconteceu.

    O critério certo é o que a pessoa usa para ter certeza de que chegou — ela
    olha o topo da página, não caça a frase no rodapé. Mencionar um destino é
    justamente o que um LINK faz; confundir menção com chegada daria TSR perfeito
    a todo site bem interligado.
    """
    from bs4 import BeautifulSoup

    sopa = BeautifulSoup(html or "", "lxml")
    cabecalhos = " ".join(t.get_text(" ", strip=True)
                          for t in sopa.find_all(["title", "h1", "h2"]))
    return palavras(marco) <= palavras(cabecalhos)


def grafo_de(paginas, arestas_de) -> dict[str, tuple[tuple[str, str], ...]]:
    """`{url: ((destino, rótulo), ...)}` a partir do que `percorrer()` devolveu.

    As ARESTAS vêm de `arestas_de` — na produção, `webqa/navegacao.py::
    links_oferecidos`, que já é a autoridade sobre o que conta como link do
    mesmo host. Este módulo não reimplementa esse julgamento: duas leituras do
    mesmo HTML divergiriam no primeiro caso de borda, e a divergência apareceria
    como um check achando link que o outro não vê.
    """
    grafo: dict[str, tuple[tuple[str, str], ...]] = {}
    for pagina in paginas:
        grafo[pagina.url] = tuple(arestas_de(pagina))
    return grafo


def saidas(grafo: Mapping[str, tuple], url: str) -> tuple[str, ...]:
    """Destinos que esta página oferece, sem contar ela mesma.

    Auto-link não é saída: uma página que só aponta para si prende tanto quanto
    uma que não aponta para lugar nenhum.
    """
    return tuple(destino for destino, _ in grafo.get(url, ()) if destino != url)


def caminho_otimo(grafo: Mapping[str, tuple], origem: str,
                  destinos: frozenset[str]) -> tuple[str, ...] | None:
    """Menor caminho (em cliques) da origem até QUALQUER destino, por BFS.

    Devolve a sequência de URLs, incluindo a origem — logo `len(caminho) - 1` é o
    número de cliques. `None` quando nenhum destino é alcançável, e isso **não é
    exceção**: alvo inalcançável é o achado (TSR = 0), não um erro do medidor.

    BFS puro, e não Dijkstra: toda aresta é um clique e custa o mesmo. Ordem de
    visita determinística (a ordem em que os links aparecem na página) para que
    duas execuções contra o mesmo alvo devolvam o mesmo caminho.
    """
    if origem in destinos:
        return (origem,)
    fila: deque[tuple[str, ...]] = deque([(origem,)])
    vistos = {origem}
    while fila:
        caminho = fila.popleft()
        for destino in saidas(grafo, caminho[-1]):
            if destino in vistos:
                continue
            vistos.add(destino)
            adiante = (*caminho, destino)
            if destino in destinos:
                return adiante
            fila.append(adiante)
    return None


def becos(grafo: Mapping[str, tuple], entrada: str) -> tuple[str, ...]:
    """Páginas em que se entra e de onde o único caminho adiante é VOLTAR.

    Critério: nenhuma saída para outra página do mesmo host. Página sem link
    nenhum É beco — a borda importa e está do lado do achado, não do lado do
    erro: "o crawler não achou link" e "não há link" são a mesma coisa para quem
    está lá, e tratar a segunda como falha de medição esconderia o defeito mais
    grosseiro que este check existe para achar.

    **A entrada fica de fora, e isso é do critério, não conveniência.** Beco é
    propriedade de página em que se ENTRA clicando; a entrada é onde se começa.
    Contá-la faria toda página única servida como alvo — uma política de
    privacidade apontada direto, por exemplo — ser reprovada por não linkar nada,
    quando o que ela é, é o começo e o fim de um documento só.
    """
    return tuple(sorted(url for url in grafo if url != entrada and not saidas(grafo, url)))


# ---------- a caminhada por rótulo ----------

def escolher_proximo(links: tuple[tuple[str, str], ...], procura: tuple[str, ...],
                     visitados: frozenset[str]) -> str | None:
    """O link que a pessoa clicaria: o rótulo mais parecido com o que procura.

    Empate resolvido pela ORDEM na página — que é a ordem em que a pessoa lê, e
    o que torna a caminhada reproduzível. `None` quando nenhum rótulo evoca a
    tarefa: é a pessoa desistindo, e desistir é resultado (TSR = 0), não erro.
    """
    melhor, melhor_nota = None, 0.0
    for destino, rotulo in links:
        if destino in visitados:
            continue
        nota = afinidade(rotulo, procura)
        if nota > melhor_nota:
            melhor, melhor_nota = destino, nota
    return melhor


def excedente(percorrido: tuple[str, ...], otimo: tuple[str, ...] | None) -> int | None:
    """Cliques a mais do que o menor caminho. `None` quando não há ótimo.

    Compara COMPRIMENTOS, e é isso que resolve o empate de ótimos de graça:
    quando há dois caminhos mínimos distintos, escolher qualquer um deles dá
    excedente zero. Comparar as SEQUÊNCIAS puniria a jornada por ter escolhido o
    ótimo "errado" — e não existe ótimo errado.
    """
    if otimo is None:
        return None
    return max(0, len(percorrido) - len(otimo))


@dataclass(frozen=True)
class Resultado:
    """O que a jornada produziu — medida, nunca veredito."""

    tarefa: Tarefa
    percorrido: tuple[str, ...] = ()
    otimo: tuple[str, ...] | None = None
    tot_ms: float = 0.0
    parou_em: str = ""
    motivo_da_parada: str = ""

    @property
    def chegou(self) -> bool:
        return not self.motivo_da_parada

    @property
    def tsr(self) -> int:
        """1 ou 0. Binário porque a pessoa chegou ou não chegou."""
        return 1 if self.chegou else 0

    @property
    def cliques(self) -> int:
        return max(0, len(self.percorrido) - 1)

    @property
    def cliques_excedentes(self) -> int | None:
        return excedente(self.percorrido, self.otimo)


def motivo_de_nao_chegar(resultado: Resultado) -> str:
    """A frase do laudo quando TSR = 0, nomeando O PASSO onde parou.

    "não chegou" sozinho não diz o que corrigir. Onde parou e o que havia ali
    para clicar é a diferença entre "a página de destino não existe" e "existe e
    ninguém a rotulou de um jeito que se ache" — correções opostas.
    """
    trilha = " → ".join(resultado.percorrido) or "(nenhuma página)"
    return (f"Tarefa {resultado.tarefa} NÃO concluída (TSR=0). "
            f"Parou em {resultado.parou_em or '(início)'} após {resultado.cliques} clique(s): "
            f"{resultado.motivo_da_parada}\nCaminho percorrido: {trilha}")


def avaliar_cliques(resultado: Resultado) -> list[str]:
    """Estouro de cliques excedentes. Puro. `None` de excedente não vira problema."""
    sobra = resultado.cliques_excedentes
    if sobra is None or sobra <= resultado.tarefa.cliques_extras_max:
        return []
    minimo = len(resultado.otimo) - 1 if resultado.otimo else 0
    return [f"{resultado.cliques} clique(s) para {resultado.tarefa.nome!r}, contra {minimo} "
            f"do menor caminho — {sobra} a mais, e a tarefa admite "
            f"{resultado.tarefa.cliques_extras_max}. Quem lê os rótulos é levado a dar voltas "
            f"que a estrutura do site não exige."]


def avaliar_tempo(resultado: Resultado) -> list[str]:
    """Estouro de ToT. Puro, e separado de `avaliar_cliques` de propósito: tempo é
    ambiente e cliques não, então os dois não podem morar no mesmo veredito."""
    if resultado.tot_ms <= resultado.tarefa.tot_ms:
        return []
    return [f"{resultado.tot_ms:.0f}ms para concluir {resultado.tarefa.nome!r}, acima do "
            f"orçamento de {resultado.tarefa.tot_ms:.0f}ms."]


def relato_de_becos(encontrados: tuple[str, ...]) -> str:
    """Um por linha, com o nome da página — é por ela que se começa a corrigir."""
    linhas = [f"  {url}" for url in encontrados]
    return ("Página(s) sem saída — quem entra só sai pelo botão Voltar:\n"
            + "\n".join(linhas))
