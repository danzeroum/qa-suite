"""Exploração assistida por LLM sobre material JÁ COLETADO (GUI-EXPL-01, OS-55).

**A LLM apresenta; o código julga.** É a regra inteira desta peça, e ela só
existe como regra porque o julgamento é mecânico: uma fricção precisa citar uma
página que o crawl viu, um tipo do vocabulário fechado e um trecho do insumo que
a sustente. Fricção que cita página inexistente é **alucinação** e morre na
validação — não vira achado marcado, não vira nota de rodapé.

**A IA processa achados já produzidos, não participa de agir contra o alvo.**
A doutrina é da casa (`tests/test_convencoes.py`) e aqui virou arquitetura: este
módulo consome grafo, rótulos e desfechos como **dados**, e não importa navegador
nem cliente HTTP. Não há como ele navegar, porque não há como ele alcançar a
rede — e há teste de convenção fixando isso.

**Fricção não é achado.** A saída fica em `report/exploratorio/`, **fora do
SARIF** e **fora do contrato**. A doutrina da OS-53 diz que achado é `failed`
medido; uma fricção é hipótese para triagem humana, e promovê-la a achado faria
o SARIF misturar o que a suíte mediu com o que um modelo sugeriu. Fora do
contrato pelo motivo mais simples de todos: saída de LLM não é determinística, e
a navalha da casa nem precisa ser invocada.

**Divergência declarada de `webqa/llm.py`.** Lá, texto que certifica é MARCADO e
entregue — é prosa para uma pessoa ler, e esconder o texto esconderia também a
tentativa. Aqui é REJEITADO: uma fricção é dado estruturado que alguém vai triar,
e uma que certifica não é triável — é ruído com forma de dado.

Somente stdlib + PyYAML (já dependência).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
PERSONAS_PADRAO = RAIZ / "data" / "personas.yaml"

# Vocabulário FECHADO. É o que transforma saída de prosa em dado triável: sem
# ele, o modelo devolve categorias novas a cada execução e nenhuma comparação
# entre duas rodadas é possível. Cada tipo é sustentável pelo material coletado —
# não há tipo que exija informação que o crawl não tem.
TIPOS_DE_FRICCAO = {
    "rotulo_ambiguo": "dois rótulos diferentes levam ao mesmo lugar, ou o rótulo não evoca o destino",
    "ausencia_de_rota": "não há caminho para algo que se espera encontrar",
    "caminho_longo": "o destino existe, mas está mais longe do que quem procura esperaria",
    "vocabulario_inconsistente": "a mesma coisa é chamada de nomes diferentes em páginas diferentes",
    "beco": "página de onde só se sai voltando",
}

# Mesma lista de `webqa/llm.py`, e a duplicação é deliberada e testada: lá a
# certificação é MARCADA, aqui é REJEITADA, então importar a função de lá traria
# o comportamento errado junto. O que se compartilha é o vocabulário, e o teste
# prova que os dois não divergiram.
# Sem `\b` no fim: a primeira versão o tinha, e ele exigia fronteira de palavra
# logo após `garantid` — mas o texto real é "garantido", e `o` é caractere de
# palavra. "conforme garantido em WCAG" passava direto. O sufixo livre (`\w*`)
# é o conserto, e o teste que o pegou usa exatamente essa frase.
_CERTIFICACAO = re.compile(
    r"(?:certificad[oa]s?|conform(?:e|idade)\s+garantid\w*|est[áa]\s+segur[oa]|"
    r"aprovad[oa]\s+em\s+wcag|100\s*%\s*acess[íi]ve[lu])", re.I)


@dataclass(frozen=True)
class Friccao:
    """Uma hipótese de fricção. NUNCA um achado — o nome é o contrato."""

    pagina: str
    tipo: str
    descricao: str
    evidencia: str
    persona: str = ""

    def __str__(self) -> str:
        return f"[{self.tipo}] {self.pagina}: {self.descricao}"


@dataclass(frozen=True)
class Rejeitada:
    """Uma saída que não sobreviveu ao julgamento, com o motivo."""

    bruta: dict
    motivo: str
    classe: str


def carregar_personas(caminho: str | Path | None = None) -> dict[str, str]:
    """Lê `data/personas.yaml`. Versionadas, nunca embutidas no prompt.

    Persona embutida no código é decisão de produto escondida em string: quem
    quiser explorar com outro olhar teria de editar Python, e a mudança não
    apareceria em diff de configuração.
    """
    dados = yaml.safe_load(Path(caminho or PERSONAS_PADRAO).read_text(encoding="utf-8")) or {}
    personas = {str(k): str(v) for k, v in (dados.get("personas") or {}).items()}
    if not personas:
        raise ValueError("data/personas.yaml não declara nenhuma persona")
    return personas


def snapshot_de(grafo: Mapping, textos: Mapping, laudo: Mapping | None = None) -> dict:
    """O insumo serializado, DETERMINÍSTICO: mesma entrada, mesmo prompt.

    Ordenado em toda parte. Sem isso, duas execuções sobre o mesmo alvo mandariam
    prompts diferentes e a diferença entre as saídas seria atribuída ao modelo
    quando veio da ordem de um dicionário.

    Recebe o grafo como DADO. Não abre página, não resolve URL, não conhece
    navegador — é o que permite este módulo existir sem violar a separação que
    `tests/test_convencoes.py` cobra.
    """
    paginas = []
    for url in sorted(grafo):
        arestas = sorted((d, r) for d, r in grafo.get(url, ()))
        paginas.append({
            "url": url,
            "titulo": str((textos or {}).get(url) or "")[:200],
            "links": [{"para": d, "rotulo": r} for d, r in arestas],
        })
    desfechos = []
    for r in sorted((laudo or {}).get("results") or [],
                    key=lambda x: str(x.get("test") or "")):
        if r.get("dimension") == "gui" and r.get("outcome") in ("failed", "xfailed"):
            desfechos.append({"teste": r.get("test"), "desfecho": r.get("outcome"),
                              "detalhe": str(r.get("detail") or "")[:300]})
    return {"paginas": paginas, "desfechos": desfechos}


def paginas_do(snapshot: Mapping) -> frozenset[str]:
    return frozenset(p["url"] for p in (snapshot.get("paginas") or []))


def _texto_do(snapshot: Mapping) -> str:
    return json.dumps(snapshot, ensure_ascii=False)


def julgar(bruta, snapshot: Mapping, persona: str = "") -> Friccao | Rejeitada:
    """O JULGAMENTO, e é aqui que a regra da peça vira mecanismo.

    Quatro portas, na ordem em que uma saída ruim costuma falhar. A ordem importa
    para a MENSAGEM: dizer "tipo inválido" quando a página também é fantasma
    mandaria quem lê consertar a coisa errada.
    """
    if not isinstance(bruta, Mapping):
        return Rejeitada(bruta={"cru": str(bruta)[:200]},
                         motivo="a saída não é um objeto com campos", classe="malformada")
    faltando = [c for c in ("pagina", "tipo", "descricao", "evidencia") if not bruta.get(c)]
    if faltando:
        return Rejeitada(bruta=dict(bruta), classe="malformada",
                         motivo=f"faltam campos obrigatórios: {faltando}")
    pagina = str(bruta["pagina"])
    if pagina not in paginas_do(snapshot):
        return Rejeitada(
            bruta=dict(bruta), classe="alucinacao",
            motivo=f"cita a página {pagina!r}, que o crawl não visitou. Fricção sobre "
                   f"página que não existe no insumo é invenção, não observação.")
    tipo = str(bruta["tipo"])
    if tipo not in TIPOS_DE_FRICCAO:
        return Rejeitada(
            bruta=dict(bruta), classe="tipo_invalido",
            motivo=f"tipo {tipo!r} fora do vocabulário fechado {sorted(TIPOS_DE_FRICCAO)}. "
                   f"Categoria nova a cada execução impede comparar duas rodadas.")
    evidencia = str(bruta["evidencia"])
    if evidencia not in _texto_do(snapshot):
        return Rejeitada(
            bruta=dict(bruta), classe="alucinacao",
            motivo=f"a evidência {evidencia[:60]!r} não aparece no insumo. Sem trecho "
                   f"que a sustente, a fricção é afirmação sobre nada.")
    if _CERTIFICACAO.search(str(bruta["descricao"])):
        return Rejeitada(
            bruta=dict(bruta), classe="certificacao",
            motivo="a descrição usa linguagem de certificação. Fricção é hipótese para "
                   "triagem; uma que certifica não é triável.")
    return Friccao(pagina=pagina, tipo=tipo, descricao=str(bruta["descricao"]),
                   evidencia=evidencia, persona=persona)


def triar(brutas, snapshot: Mapping, persona: str = "") -> tuple[list, list]:
    """(aceitas, rejeitadas). Nada é descartado em silêncio — o que morreu na
    validação vai para o relatório com o motivo, porque a taxa de alucinação é
    ela própria um dado sobre o modelo."""
    aceitas, rejeitadas = [], []
    for bruta in (brutas or []):
        resultado = julgar(bruta, snapshot, persona)
        (aceitas if isinstance(resultado, Friccao) else rejeitadas).append(resultado)
    return aceitas, rejeitadas


# ---------- o prompt, escrito DEPOIS do validador ----------

INSTRUCAO = (
    "Você recebe o mapa de um site JÁ percorrido: páginas, títulos e os rótulos "
    "dos links entre elas. Você NÃO pode navegar, clicar ou pedir mais dados.\n\n"
    "Aponte fricções que alguém enfrentaria para se orientar nesse mapa.\n\n"
    "Responda APENAS um array JSON. Cada item:\n"
    '  {"pagina": "<url EXATA do insumo>", "tipo": "<um dos tipos>", '
    '"descricao": "<uma frase>", "evidencia": "<trecho LITERAL do insumo>"}\n\n'
    "Tipos válidos: {tipos}\n\n"
    "Regras que invalidam o item:\n"
    "- página que não esteja no insumo;\n"
    "- evidência que não apareça literalmente no insumo;\n"
    "- tipo fora da lista;\n"
    "- dizer que algo é seguro, conforme, certificado ou acessível — você não "
    "tem como saber isso, e não é o seu papel.\n\n"
    "Não invente páginas para completar a lista. Zero fricções é uma resposta "
    "válida."
)


def montar_prompt(snapshot: Mapping, persona_nome: str, persona_texto: str) -> str:
    """O prompt. Escrito DEPOIS do validador, de propósito.

    Prompt primeiro produz prosa bonita que nenhum código consegue julgar, e "o
    código julga" viraria letra morta no único lugar da suíte onde ela era a
    regra inteira. As regras abaixo são a *tradução* das portas de `julgar` —
    o modelo é informado do que será verificado, e o que ele responder passa
    pela verificação de qualquer jeito.
    """
    # `replace` e não `.format`: a INSTRUCAO contém o JSON de exemplo, com
    # chaves literais, e `.format` as trata como campos e estoura com
    # KeyError: '"pagina"'. Foi assim que a primeira versão quebrou — o exemplo
    # que existe para o modelo acertar o formato quebrava quem montava o prompt.
    instrucao = INSTRUCAO.replace("{tipos}", ", ".join(sorted(TIPOS_DE_FRICCAO)))
    return (f"{instrucao}\n\n"
            f"Olhe como esta persona: {persona_nome} — {persona_texto}\n\n"
            f"MAPA:\n{json.dumps(snapshot, ensure_ascii=False, indent=1)}")
