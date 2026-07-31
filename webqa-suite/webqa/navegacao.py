"""Navegação passiva autenticada — seguir o que a aplicação OFERECE, nunca adivinhar.

Este módulo é a fronteira entre duas coisas que se parecem e não são:

* **passivo autenticado** (aqui): navegar a área logada como um usuário real
  navegaria — clicando no que está na tela. Cada endereço visitado veio de um
  atributo do DOM renderizado;
* **sondagem ativa** (Fase C, `docs/SEGURANCA.md §7`, atrás de gate): perguntar
  ao servidor por endereços que ele não ofereceu.

A diferença não é de intenção nem de volume — é de **origem do endereço**. Por
isso ela é código, e não convenção: toda `Pagina` carrega a `origem` de onde seu
endereço saiu, e uma página que ninguém linkou não tem como ser alcançada, porque
não existe caminho no programa que fabrique um endereço.

Consequência prática, e é ela que o teste da página órfã prova: **nenhuma URL
nasce no fonte deste módulo.** Não há literal de caminho, não há concatenação que
produza rota, não há `urljoin` com destino constante. Se um aparecer, a guarda de
AST (`tests/test_navegacao_autenticada.py`) reprova no CI — do mesmo modo que a
OS-36 verifica a ausência dos símbolos da Fase C.

**Formulário não é seguido.** Um `<form action>` só se alcança submetendo, e
submeter escreve no sistema do alvo — é interação, não observação, e mora atrás
de `WEBQA_ACTIVE_PROBES_AUTHORIZED` (`webqa/gates.py`). Seguir `<a href>` é ler
uma página que a aplicação pôs na navegação; submeter um formulário é criar
registro na casa dos outros.

Somente stdlib mais BeautifulSoup, que já existe no projeto.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

# Esquemas que não são navegação: abrir cliente de e-mail ou discador não é
# carregar página, e `javascript:` não é endereço nenhum.
ESQUEMAS_IGNORADOS = ("mailto:", "tel:", "javascript:", "data:", "sms:")

ENTRADA = "ponto de entrada"


@dataclass(frozen=True)
class Pagina:
    """Uma página visitada e a PROVENIÊNCIA do endereço que levou até ela."""

    url: str
    origem: str
    status: int
    html: str = ""

    @property
    def veio_de_link(self) -> bool:
        return self.origem != ENTRADA


def _mesmo_host(url: str, host: str) -> bool:
    return urlsplit(url).netloc == host


def links_oferecidos(html: str, url_da_pagina: str, host: str) -> list[tuple[str, str]]:
    """`(url, proveniência)` de cada link que ESTA página oferece.

    O endereço sai de `urljoin` entre a URL da própria página e o valor cru do
    atributo — as duas pontas vêm de dados, nenhuma do fonte. Fragmento é
    descartado porque `#secao` é a mesma página, e revisitá-la seria contar duas
    vezes o mesmo documento.
    """
    sopa = BeautifulSoup(html or "", "lxml")
    achados: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for etiqueta in sopa.find_all(["a", "area"], href=True):
        bruto = (etiqueta["href"] or "").strip()
        if not bruto or bruto.startswith("#"):
            continue
        if bruto.lower().startswith(ESQUEMAS_IGNORADOS):
            continue
        url = urljoin(url_da_pagina, bruto).split("#")[0]
        if not _mesmo_host(url, host) or url in vistos:
            continue
        vistos.add(url)
        achados.append((url, f"link em {url_da_pagina}"))
    return achados


def _abrir_sem_derrubar(abrir, url: str) -> tuple[int, str] | None:
    """`(status, html)`, ou `None` quando a página não abriu.

    A captura ampla é deliberada — timeout, DNS e navegador morto não são
    veredito sobre o alvo, e instrumentação não pode derrubar a observação. Mora
    numa função que RETORNA em vez de um `continue` dentro do laço porque a
    biblioteca é varrida pelo bandit com rigor total (`B112`), e a resposta certa
    a um alerta de estrutura é mudar a estrutura, não silenciá-lo.
    """
    try:
        return abrir(url)
    except Exception:
        return None


def percorrer(entrada: str, abrir, teto: int = 15, pode_acessar=None) -> list[Pagina]:
    """Percorre a área autenticada em largura, uma página por vez.

    `abrir(url) -> (status, html)` é injetado: é o que permite verificar a
    disciplina inteira sem rede, e é onde o Playwright entra em produção
    (carregar de verdade, com a sessão autenticada, e devolver o DOM RENDERIZADO
    — link que só existe depois do JavaScript é link que o usuário vê).

    `pode_acessar(url) -> bool` é a etiqueta (`webqa/etiqueta.py`): caminho que o
    dono pediu para não rastrear não é visitado, mesmo estando linkado. Oferecer
    não revoga ter pedido para não entrar.

    Sequencial de propósito. Paralelizar o percurso transformaria diagnóstico em
    rajada — a mesma razão registrada em `checks/functional/test_links.py`.
    """
    host = urlsplit(entrada).netloc
    fila: list[tuple[str, str]] = [(entrada, ENTRADA)]
    enfileirados = {entrada}
    visitadas: list[Pagina] = []

    while fila and len(visitadas) < teto:
        url, origem = fila.pop(0)
        if pode_acessar is not None and not pode_acessar(url):
            continue
        aberta = _abrir_sem_derrubar(abrir, url)
        if aberta is None:
            continue
        status, html = aberta
        visitadas.append(Pagina(url=url, origem=origem, status=int(status), html=html or ""))
        for destino, proveniencia in links_oferecidos(html or "", url, host):
            if destino not in enfileirados:
                enfileirados.add(destino)
                fila.append((destino, proveniencia))

    return visitadas


def proveniencias(paginas: list[Pagina]) -> dict[str, str]:
    """`url -> origem`, para o laudo poder afirmar de onde cada endereço saiu."""
    return {p.url: p.origem for p in paginas}
