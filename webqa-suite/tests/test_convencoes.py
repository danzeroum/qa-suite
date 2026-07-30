"""VERIFICAÇÃO das convenções que já morderam este projeto (OS-32).

As três armadilhas cobertas aqui não são hipóteses de manual: cada uma custou
uma sessão de depuração, e duas reincidiram. Até esta OS elas viviam só em
comentário — e comentário não reprova ninguém.

O padrão comum às três merece nome, porque é o que as torna previsíveis:
**prosa e código discordaram, e a prosa estava certa.** O docstring dizia
"função auxiliar", o pytest coletou como teste. O comentário dizia "folga de
20%", a saída imprimiu 19%. O doc dizia "remove identificação de alvo", e o
campo `origens` levava o host no caminho.

Quando os dois discordam, a suspeita começa pelo código: a prosa foi escrita
com a intenção à vista, o código foi escrito com a implementação à vista, e é a
implementação que erra em silêncio.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent

# Pastas de BIBLIOTECA e FERRAMENTA — nada aqui é módulo de teste. `checks/` e
# `tests/` ficam de fora porque lá o prefixo é justamente o que se quer.
PASTAS_SEM_TESTES = ("webqa", "scripts", "fixture_target")

# O pytest coleta por `python_functions = test*` (default; `pytest.ini` não
# sobrescreve). É PREFIXO "test", não "test_" — e a diferença é exatamente o
# bug da OS-31: `testes_lentos` não começa com "test_", começa com "test", e foi
# coletada assim mesmo. Uma guarda que checasse "test_" não pegaria o caso que
# ela existe para prevenir.
PREFIXO_DE_COLETA = "test"

# Casos legítimos, se algum dia houver. Vazia de propósito: nome no plural em
# português ("testes", "testar") cai no prefixo sem querer, e é bom que doa.
ALLOWLIST: frozenset[str] = frozenset()


def _funcoes_de(caminho: Path) -> list[tuple[str, int]]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return [(no.name, no.lineno) for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)]


def test_biblioteca_nao_tem_funcao_com_prefixo_de_coleta():
    """Função `test*` fora de módulo de teste é coletada como teste — e pior,
    contamina QUALQUER módulo que a importe pelo nome.

    Aconteceu duas vezes. Na OS-28, `from ... import test_svg_...` fez o pytest
    coletar checks reais dentro do arquivo de verificação, que subiram navegador
    contra o alvo configurado no meio de uma bateria offline. Na OS-31,
    `testes_lentos` — uma função de agregação — foi coletada e reprovou pedindo
    uma fixture `summaries` que nunca existiu.

    O segundo caso é o mais traiçoeiro: o nome nasce inocente em português.
    """
    ofensores = []
    for pasta in PASTAS_SEM_TESTES:
        for arquivo in sorted((RAIZ / pasta).glob("*.py")):
            for nome, linha in _funcoes_de(arquivo):
                if nome.startswith(PREFIXO_DE_COLETA) and nome not in ALLOWLIST:
                    ofensores.append(f"{arquivo.relative_to(RAIZ)}:{linha} → {nome}()")

    assert not ofensores, (
        "função com prefixo de coleta do pytest fora de módulo de teste:\n  "
        + "\n  ".join(ofensores)
        + "\nO pytest coleta por `test*` (não `test_*`), então `testes_x` e "
          "`testar_y` também entram. Renomeie — o prefixo vira mina em qualquer "
          "módulo que importe o nome, não só neste arquivo."
    )


def test_a_guarda_pega_o_caso_que_a_motivou():
    """Prova que a regra reprova `testes_lentos`, e não só `test_lentos`.

    Sem isto, alguém "simplificaria" a checagem para `test_` e a guarda passaria
    a aprovar exatamente o bug da OS-31 — em silêncio, porque a suíte seguiria
    verde.
    """
    for nome in ("testes_lentos", "test_lentos", "testar_alvo", "teste"):
        assert nome.startswith(PREFIXO_DE_COLETA), (
            f"{nome!r} é coletado pelo pytest e a guarda precisa enxergá-lo")
    for nome in ("ranking_de_lentos", "montar", "atestar", "protesto"):
        assert not nome.startswith(PREFIXO_DE_COLETA), (
            f"{nome!r} não é coletado; a guarda não pode reclamar dele")


def test_modulos_de_teste_seguem_livres_para_usar_o_prefixo():
    """A guarda vale para biblioteca e ferramenta, não para `tests/` — lá o
    prefixo é o mecanismo, não o acidente."""
    daqui = [n for n, _ in _funcoes_de(Path(__file__))
             if n.startswith(PREFIXO_DE_COLETA)]
    assert len(daqui) >= 3, "este próprio arquivo precisa de funções test*"
