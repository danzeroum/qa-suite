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


# ---------- Invariantes ESTÁTICAS da Fase C (verificação, não runtime) ----------
#
# Preventivas, não cicatrizes: diferente das três acima, estas não morderam
# ainda — existem porque o motor de sondagem (C1) ainda não foi escrito, e a hora
# de fixar a convenção é ANTES de haver código para consertar. São verificação
# pura (o tree está correto?); a validação do comportamento é dos testes de
# runtime que já existem (gates, escopo, o teste da trava). Robustas à ausência:
# sem `webqa/sondagem.py`, varrem `checks/` de hoje e passam vazias.

# Espelha `test_fase_c_travada.SIMBOLOS_DA_FASE_C`. Duplicado de propósito, como
# os detectores da casa: cada guarda é autônoma, e o auto-teste abaixo prova que
# esta lista morde.
SIMBOLOS_DE_SONDAGEM = ("probe_path", "sondar_caminho", "fetch_map", "baixar_map",
                        "follow_sublinks", "seguir_sublinks", "baixar_extras")


def _e_modulo_de_sondagem(arvore: ast.AST, stem: str) -> bool:
    """O módulo é (ou será) motor de sondagem ativa?

    Dois sinais: o nome do arquivo (`sondagem.py`) ou a definição de um símbolo
    de sondagem. Assim vale para quando o motor existir e para um símbolo que
    escape para `checks/` hoje.
    """
    if "sondagem" in stem:
        return True
    return any(
        isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and no.name in SIMBOLOS_DE_SONDAGEM
        for no in ast.walk(arvore))


def _linhas_que_importam_llm(arvore: ast.AST) -> list[int]:
    """Linhas onde o módulo importa a camada `llm`, em qualquer das formas.

    Por AST, não por substring: `# não usa llm` num comentário ou `"llm"` numa
    string não é import, e reprovar quem explica ensina a não explicar.
    """
    linhas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            modulo = no.module or ""
            if modulo == "llm" or modulo == "webqa.llm" or modulo.endswith(".llm"):
                linhas.append(no.lineno)               # from webqa.llm import X
            elif modulo in ("webqa", "") and any(a.name == "llm" for a in no.names):
                linhas.append(no.lineno)               # from webqa import llm / from . import llm
        elif isinstance(no, ast.Import):
            if any(a.name == "llm" or a.name.endswith(".llm") for a in no.names):
                linhas.append(no.lineno)               # import webqa.llm
    return linhas


def _find_secrets_sem_fase(arvore: ast.AST) -> list[int]:
    """Linhas de chamadas a `find_secrets(...)` SEM o argumento nomeado `fase=`.

    Nomeado de propósito: `find_secrets` já exige `fase` (C0c), mas um terceiro
    posicional é fácil de trocar de lugar quando alguém acrescenta um parâmetro.
    `fase=` explícito deixa a fase auditável no ponto de chamada — e um achado de
    sondagem etiquetado como passivo por engano é exatamente o que se evita.
    """
    linhas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", None)
        if nome == "find_secrets" and not any(k.arg == "fase" for k in no.keywords):
            linhas.append(no.lineno)
    return linhas


def _arvores(*pastas: str):
    """(caminho relativo, árvore) de cada `.py` das pastas dadas — recursivo."""
    for pasta in pastas:
        for arquivo in sorted((RAIZ / pasta).rglob("*.py")):
            yield arquivo, ast.parse(arquivo.read_text(encoding="utf-8"))


# ---- os detectores, provados antes de varrer o tree ----

def test_o_detector_de_import_llm_pega_um_plantado():
    """Um módulo de sondagem que importa llm — o acoplamento proibido."""
    fonte = ("from webqa.llm import ResumidorLocal\n\n"
             "def probe_path(client, caminho):\n    return client.head(caminho)\n")
    arvore = ast.parse(fonte)
    assert _e_modulo_de_sondagem(arvore, "qualquer") is True
    assert _linhas_que_importam_llm(arvore) == [1]


def test_o_detector_de_import_llm_ignora_prosa_e_nao_sondagem():
    """`llm` em docstring/comentário não é import; e módulo que não faz sondagem
    pode importar llm à vontade (o `scripts/sumario.py` faz)."""
    prosa = ast.parse('"""Este módulo NÃO importa llm."""\n# nem aqui: llm\n')
    assert _linhas_que_importam_llm(prosa) == []
    nao_sondagem = ast.parse("from webqa import llm\n\ndef resumir():\n    return llm\n")
    assert _e_modulo_de_sondagem(nao_sondagem, "sumario") is False


def test_o_detector_de_find_secrets_pega_chamada_sem_fase():
    com_fase = ast.parse('find_secrets(t, r, fase="C")\n')
    sem_fase = ast.parse('find_secrets(t, r)\n')
    posicional = ast.parse('find_secrets(t, r, "C")\n')   # posicional não é explícito
    assert _find_secrets_sem_fase(com_fase) == []
    assert _find_secrets_sem_fase(sem_fase) == [1]
    assert _find_secrets_sem_fase(posicional) == [1]


# ---- a varredura de verdade ----

def test_modulo_de_sondagem_nao_importa_llm():
    """Separação de processo: o motor que AGE contra o alvo (sondagem) não pode
    importar a camada que PROCESSA achados (llm). Misturar as duas é acoplar
    autorização de sondagem com execução de IA — cada mistura é uma autorização
    que ninguém deu. Vazia hoje (sem motor); vale quando `sondagem.py` existir."""
    ofensores = []
    for arquivo, arvore in _arvores("webqa", "checks"):
        if not _e_modulo_de_sondagem(arvore, arquivo.stem):
            continue
        for linha in _linhas_que_importam_llm(arvore):
            ofensores.append(f"{arquivo.relative_to(RAIZ)}:{linha} → módulo de sondagem importa llm")

    assert not ofensores, (
        "módulo de sondagem ativa importando a camada llm:\n  " + "\n  ".join(ofensores)
        + "\nO motor de sondagem não conhece a LLM — a IA processa achados já "
          "produzidos, não participa de agir contra o alvo (docs/LLM.md, gates.py).")


def test_find_secrets_sempre_com_fase_explicita():
    """Toda chamada a `find_secrets` no código de produção nomeia `fase=`."""
    ofensores = []
    for arquivo, arvore in _arvores("webqa", "checks", "scripts", "fixture_target"):
        for linha in _find_secrets_sem_fase(arvore):
            ofensores.append(f"{arquivo.relative_to(RAIZ)}:{linha} → find_secrets sem fase=")

    assert not ofensores, (
        "chamada a find_secrets sem `fase=` explícito:\n  " + "\n  ".join(ofensores)
        + "\nPasse fase= no ponto de chamada (A/B/C). Terceiro posicional é fácil "
          "de deslocar e etiqueta o achado com a fase errada em silêncio.")
