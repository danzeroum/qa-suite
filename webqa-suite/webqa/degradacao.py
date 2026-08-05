"""Degradação da interface quando a API falha — o núcleo puro do GUI-RESIL.

Nielsen **H9** (ajudar a reconhecer, diagnosticar e recuperar-se de erros) e
**H1** (visibilidade do estado); ISO 25010, tolerância a falhas. Tela branca sob
500 é o pior defeito de interface que existe, e nada na suíte o pegava.

**A fronteira, porque um leitor apressado lê "simular 500" e pensa em sondagem
ativa.** A interceptação acontece no CLIENTE (`page.route`): o alvo recebe
*menos* requisições, nunca mais, e nunca uma que ele não tenha oferecido. É
passivo pelo critério de `docs/GUI.md §2.1` e não exige gate. E só endpoint de
MESMA ORIGEM é interceptado — terceiro nunca, mesma disciplina da bateria LGPD.

**Três desfechos, e a diferença entre eles é a tese deste módulo:**

* **tela branca** e **termo técnico vazado** são inequívocos e reprovam. Não
  dependem de idioma, de público nem de opinião: ou existe conteúdo principal,
  ou não; ou a tela mostra `SyntaxError`, ou não;
* **ausência de mensagem compreensível** é SINAL, não prova, e vira `xfail`. A
  heurística é um vocabulário de palavras, e vocabulário não cobre alvo
  internacionalizado. Reprovar com heurística fraca custa a credibilidade da
  bateria inteira — o mesmo argumento que `webqa/sanitize.py` usa para recusar
  detecção de segredo por entropia.

**Por que o texto visível, e não o HTML.** Um termo proibido dentro de
`<script>`, de um comentário ou de um atributo não está na tela de ninguém —
`undefined is not a function` aparece no fonte de meia internet. Contar isso
reprovaria alvo conforme, que é o defeito mais caro que uma bateria pode ter.
`texto_visivel` derruba `script`, `style`, `template`, `noscript` e `head`, e
respeita `hidden`, `aria-hidden` e `display:none` inline.

**Limite declarado:** elemento escondido por folha de estilo EXTERNA é contado
como visível — a avaliação é sobre o DOM serializado, sem CSSOM. A direção do
erro é conhecida e escolhida: o termo técnico continua tendo sido entregue ao
navegador, a um `display:block` de distância da tela.

Somente stdlib + bs4/lxml (já dependência, e já a ferramenta de HTML da casa).
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from webqa.sanitize import sanitize_text
from webqa.viewports import PERFIS_PADRAO

# Não renderizam texto na tela. `head` inteiro porque `<title>` é do navegador,
# não da página, e `template` porque o conteúdo só existe se alguém o clonar.
TAGS_SEM_TEXTO = ("script", "style", "template", "noscript", "head")

# Recursos que a página busca por JavaScript. `resource_type` do Playwright:
# `xhr` para XMLHttpRequest e `fetch` para a Fetch API.
TIPOS_XHR = ("xhr", "fetch")

# Teto de endpoints interceptados. Interceptar tudo transformaria o check numa
# simulação de "a internet caiu", que é outro cenário e tem outro nome.
TETO_DE_ENDPOINTS = 3


@dataclass(frozen=True)
class Vocabulario:
    """O que `data/gui-perfis.yaml` diz sobre mensagens de erro."""

    termos_proibidos: tuple[str, ...] = ()
    vocabulario_de_erro: tuple[str, ...] = ()


@dataclass(frozen=True)
class Laudo:
    """O que o DOM final revelou. Observação, não veredito — quem decide é o check."""

    tela_branca: bool = False
    termos_vazados: tuple[str, ...] = ()
    mensagem_visivel: bool = False
    trecho: str = ""
    novidades: tuple[str, ...] = field(default=(), repr=False)


def texto_visivel(dom: str) -> str:
    """O texto que chega à tela, e só ele.

    Termo proibido em comentário, atributo ou `<script>` NÃO conta: não está na
    tela de ninguém, e contá-lo reprovaria metade da internet pelo fonte de uma
    biblioteca.
    """
    sopa = BeautifulSoup(dom or "", "lxml")
    for tag in sopa.find_all(TAGS_SEM_TEXTO):
        tag.decompose()
    for tag in sopa.find_all(_escondido):
        tag.decompose()
    return sopa.get_text("\n")


def _escondido(tag) -> bool:
    """Escondido pelo próprio elemento — atributo ou estilo inline.

    Só o que está NO elemento: sem CSSOM não há como saber o que uma folha
    externa escondeu, e adivinhar seria pior que declarar o limite.
    """
    if tag.has_attr("hidden") or tag.get("aria-hidden") == "true":
        return True
    estilo = "".join((tag.get("style") or "").split()).lower()
    return "display:none" in estilo or "visibility:hidden" in estilo


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def _sem_acento(texto: str) -> str:
    """`indisponível` e `indisponivel` são a mesma palavra para quem lê a tela."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def avaliar(dom: str, saudavel: str = "", *, vocabulario: Vocabulario) -> Laudo:
    """Compara o DOM degradado com o da carga saudável e descreve a diferença.

    A comparação com a carga saudável não é refinamento: sem ela, um rodapé que
    diz "em caso de erro, ligue para…" seria lido como resposta à falha, e todo
    alvo com a palavra "erro" em algum canto passaria sem tratar nada. Mensagem
    de erro é a que APARECEU por causa da falha.

    Os termos proibidos, ao contrário, valem sobre TODO o texto visível: um
    `SyntaxError` que já estava na tela antes não é menos vazamento.
    """
    visivel = texto_visivel(dom)
    novidades = tuple(linha for linha in _linhas(visivel)
                      if linha not in set(_linhas(texto_visivel(saudavel))))
    normalizado = _sem_acento(visivel)
    vazados = tuple(termo for termo in vocabulario.termos_proibidos
                    if _sem_acento(termo) in normalizado)
    novo = _sem_acento("\n".join(novidades))
    return Laudo(
        tela_branca=not _principal(dom),
        termos_vazados=vazados,
        mensagem_visivel=any(_sem_acento(p) in novo for p in vocabulario.vocabulario_de_erro),
        # SÓ o que é novo. Cair para o texto inteiro quando nada mudou faria a
        # evidência do silêncio parecer a página inteira aparecendo — que é o
        # oposto do que aconteceu, e manda quem lê o laudo investigar o nada.
        trecho=_trecho(novidades),
        novidades=novidades,
    )


def _principal(dom: str) -> str:
    """Texto da região principal: `<main>`, `[role=main]` ou, na falta, o `body`.

    O fallback para `body` é deliberado: alvo sem `<main>` não pode ser lido como
    alvo sem conteúdo — isso transformaria uma ausência de marcação semântica em
    acusação de tela branca, que é outra coisa e tem outro check.
    """
    sopa = BeautifulSoup(dom or "", "lxml")
    for tag in sopa.find_all(TAGS_SEM_TEXTO):
        tag.decompose()
    regiao = sopa.find("main") or sopa.find(attrs={"role": "main"}) or sopa.body
    return (regiao.get_text(" ").strip() if regiao else "")


def _trecho(linhas: Iterable[str], teto: int = 5) -> str:
    """Evidência em TEXTO, sanitizada — e é o que sustenta o achado sozinho.

    Esta é a spec de maior risco de PII do conjunto: tela de erro de aplicação
    real costuma exibir dado de quem estava logado. Por isso a evidência é
    seletor e texto, nunca pixel, e o texto passa pela borda de escrita da casa
    (`webqa/sanitize.py`) antes de existir como string.
    """
    escolhidas = list(linhas)[:teto]
    return "\n".join(f"  {sanitize_text(linha)[:200]}" for linha in escolhidas)


def excedeu_tentativas(tentativas: int, teto: float) -> bool:
    """Laço de repetição contra um endpoint que já falhou.

    O comparador é `>`, não `>=`: repetição com recuo exponencial é comportamento
    LEGÍTIMO e desejável, e o teto existe para separar "tentou de novo" de "está
    martelando o servidor caído". No teto exato a página ainda está dentro do que
    se pede dela.
    """
    return tentativas > teto


def endpoints_de_mesma_origem(requisicoes, origem: str,
                              teto: int = TETO_DE_ENDPOINTS) -> tuple[str, ...]:
    """Endpoints XHR/fetch da MESMA origem, do mais chamado para o menos.

    Descoberta passiva: são os endereços que a própria página pediu durante uma
    carga normal. Nada é adivinhado, nada é enumerado — a mesma doutrina de
    `webqa/navegacao.py::percorrer`, onde página que ninguém linkou não existe.

    Terceiro fica de fora por regra, não por eficiência: interceptar a chamada de
    um alvo a um serviço de terceiro não observaria a resiliência do alvo, e
    ainda faria a suíte agir sobre uma relação que não é dela.
    """
    prefixo = origem.rstrip("/") + "/"
    volume: dict[str, int] = {}
    for requisicao in requisicoes:
        url, tipo = _url_e_tipo(requisicao)
        if tipo not in TIPOS_XHR:
            continue
        if not (url == origem.rstrip("/") or url.startswith(prefixo)):
            continue
        limpa = url.split("#", 1)[0]
        volume[limpa] = volume.get(limpa, 0) + 1
    ordenados = sorted(volume.items(), key=lambda par: (-par[1], par[0]))
    return tuple(url for url, _ in ordenados[:teto])


def _url_e_tipo(requisicao) -> tuple[str, str]:
    if isinstance(requisicao, (tuple, list)):
        return str(requisicao[0]), str(requisicao[1])
    return str(getattr(requisicao, "url", "")), str(getattr(requisicao, "resource_type", ""))


def carregar_vocabulario(caminho: str | Path | None = None) -> Vocabulario:
    """Lê o bloco `resiliencia` de `data/gui-perfis.yaml`.

    Vocabulário em YAML e não no código porque ele é decisão de quem opera a
    suíte: alvo em espanhol precisa de outras palavras, e trocar uma lista de
    palavras não deveria exigir um PR na biblioteca.
    """
    dados = yaml.safe_load(Path(caminho or PERFIS_PADRAO).read_text(encoding="utf-8")) or {}
    bruto = dados.get("resiliencia") or {}
    return Vocabulario(
        termos_proibidos=tuple(str(t) for t in (bruto.get("termos_proibidos") or [])),
        vocabulario_de_erro=tuple(str(t) for t in (bruto.get("vocabulario_de_erro") or [])),
    )
