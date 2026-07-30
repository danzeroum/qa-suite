"""VERIFICAÇÃO de que a Fase C continua travada (OS-36).

Aqui não se testa **ação** nenhuma — testa-se a **recusa**. Nenhuma linha de
sondagem ativa é escrita, e nenhuma requisição sai: o que se prova é que, sem
`WEBQA_ACTIVE_PROBES_AUTHORIZED=1`, nada acontece; que a fronteira é estrutural
e não convenção; e que os dois gates são independentes.

Por que agora, com a Fase C ainda travada: enquanto "travada" for promessa, ela
depende de vigilância humana — e vigilância humana é exatamente o que este
projeto substitui por invariante estrutural em todo lugar (o `Finding` que
sanitiza no construtor, o teste que lê o fonte da Fase B e reprova `httpx`). No
dia em que houver alvo autorizado, a capacidade nasce sobre uma fronteira **já
provada**, não sobre uma frase num documento.

O detector é o coração deste arquivo, e ele próprio é testado: um detector de
violação que nunca detectou uma violação plantada não está provado.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from webqa import gates

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
CHECKS = RAIZ / "checks"

# Caminhos que só se alcança PERGUNTANDO ao servidor por algo que ele não
# ofereceu. Sondá-los é a linha que separa auditoria de intrusão
# (docs/SEGURANCA.md §1) — e é o que a Fase C faria, atrás do gate.
CAMINHOS_DE_SONDAGEM = (
    "/.git", "/.env", "/backup.zip", "/.DS_Store", "/wp-config", "/.htpasswd",
)

# Nomes que só existiriam se a Fase C tivesse sido codificada. A ausência é
# deliberada, e verificá-la é o que impede a capacidade de nascer sem revisão.
SIMBOLOS_DA_FASE_C = ("probe_path", "sondar_caminho", "fetch_map", "baixar_map",
                      "follow_sublinks", "seguir_sublinks", "baixar_extras")


def _docstrings(arvore: ast.AST) -> set[int]:
    """`id()` dos nós que são docstring — texto, não código.

    Um literal citado na documentação (`docs/SEGURANCA.md §7` fala de `/.git/HEAD`
    por extenso) não é sondagem. Comentários nem chegam aqui: o `ast` os
    descarta, então são livres por construção.
    """
    ignorar = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        corpo = getattr(no, "body", [])
        if (corpo and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)):
            ignorar.add(id(corpo[0].value))
    return ignorar


def sondagens_em(fonte: str, arquivo: str = "<memória>") -> list[str]:
    """Literais de caminho sensível FORA de docstring. Vazio = limpo.

    Pública de propósito: o teste do próprio detector a chama com fonte
    fabricado, e uma função privada obrigaria o teste a mexer em interno.
    """
    arvore = ast.parse(fonte)
    ignorar = _docstrings(arvore)
    achados = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Constant) and isinstance(no.value, str)):
            continue
        if id(no) in ignorar:
            continue
        for caminho in CAMINHOS_DE_SONDAGEM:
            if caminho in no.value:
                achados.append(f"{arquivo}:{no.lineno} → {no.value[:60]!r} contém {caminho!r}")
    return achados


# ---------- o detector, provado antes de ser usado ----------

def test_o_detector_pega_sondagem_plantada():
    """Um detector que nunca detectou violação plantada não está provado.

    Este é o teste que dá autoridade a todos os outros deste arquivo: se ele
    passar por engano, a varredura de `checks/` vira teatro.
    """
    fabricado = '''
"""Docstring citando /.git/HEAD — isto é documentação, não sondagem."""
import httpx

def sondar(client):
    return client.get("/.git/HEAD")
'''
    achados = sondagens_em(fabricado, "fabricado.py")
    assert len(achados) == 1, f"esperava 1 achado, veio {achados}"
    assert "/.git" in achados[0]

    # A linha é DERIVADA do fonte, não escrita à mão: literal aqui quebra a cada
    # ajuste de espaçamento no exemplo e ensina a "consertar" o número em vez de
    # olhar o que mudou.
    linha_da_sondagem = next(i for i, texto in enumerate(fabricado.splitlines(), start=1)
                             if "client.get" in texto)
    linha_da_docstring = next(i for i, texto in enumerate(fabricado.splitlines(), start=1)
                              if "Docstring" in texto)
    assert f":{linha_da_sondagem}" in achados[0], "aponta a sondagem"
    assert f":{linha_da_docstring}" not in achados[0], "a docstring não é sondagem"


@pytest.mark.parametrize("caminho", CAMINHOS_DE_SONDAGEM)
def test_o_detector_pega_cada_caminho_da_lista(caminho):
    """Cada entrada da lista precisa disparar — lista com item morto engana."""
    assert sondagens_em(f'x = client.get("{caminho}/algo")', "f.py")


def test_o_detector_ignora_docstring_e_nao_produz_falso_positivo():
    """`docs/SEGURANCA.md §7` cita esses caminhos por extenso, e um módulo pode
    explicar por que NÃO os sonda. Explicar não é fazer."""
    fabricado = '''
"""Fase C sondaria /.git/HEAD, /.env e /backup.zip — desenhada, não implementada."""

def analisar(corpo):
    # comentário mencionando /.env também é livre
    return len(corpo)
'''
    assert sondagens_em(fabricado, "f.py") == []


def test_fonte_limpo_passa():
    assert sondagens_em("def f(x):\n    return x.upper()\n", "f.py") == []


# ---------- a varredura de verdade ----------

def test_nenhum_check_sonda_caminho_sensivel():
    """Toda a árvore de `checks/`, hoje e a cada PR.

    Se alguém colar sondagem — por descuido, por copiar de um scanner, ou por
    achar que "é só um GET" — isto reprova ANTES do merge, com arquivo e linha.
    """
    ofensores = []
    for arquivo in sorted(CHECKS.rglob("*.py")):
        ofensores += sondagens_em(arquivo.read_text(encoding="utf-8"),
                                  str(arquivo.relative_to(RAIZ)))

    assert not ofensores, (
        "sondagem de caminho não oferecido pelo servidor em checks/:\n  "
        + "\n  ".join(ofensores)
        + "\nIsso é Fase C (docs/SEGURANCA.md §7), exige "
          f"{gates.ACTIVE_PROBES_ENV}=1 e autorização escrita do dono de um alvo. "
          "Pedir ao servidor o que ele não ofereceu é intrusão, não auditoria.")


def test_fase_c_nao_existe_ainda():
    """A ausência dos símbolos é intencional — e verificada.

    Não é sobre o nome: é sobre a capacidade. Se um deles aparecer, alguém
    começou a codificar a sondagem ativa, e isso precisa passar por revisão
    consciente em vez de entrar de carona num PR sobre outra coisa.
    """
    definidos = []
    for arquivo in sorted(CHECKS.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                if no.name in SIMBOLOS_DA_FASE_C:
                    definidos.append(f"{arquivo.relative_to(RAIZ)}:{no.lineno} → {no.name}")

    assert not definidos, (
        "símbolo de sondagem ativa definido em checks/:\n  " + "\n  ".join(definidos)
        + "\nA Fase C está desenhada e NÃO implementada de propósito. Construir "
          "capacidade intrusiva antes de haver alvo autorizado é YAGNI com peso ético.")


def test_o_detector_de_simbolo_pega_um_plantado():
    """Prova que a ausência acima significa alguma coisa."""
    arvore = ast.parse("def follow_sublinks(page):\n    return []\n")
    nomes = [no.name for no in ast.walk(arvore)
             if isinstance(no, ast.FunctionDef) and no.name in SIMBOLOS_DA_FASE_C]
    assert nomes == ["follow_sublinks"]


# ---------- o gate não liga por default ----------

@pytest.fixture
def ambiente_limpo(monkeypatch):
    for env in (gates.LOAD_ENV, gates.ACTIVE_PROBES_ENV):
        monkeypatch.delenv(env, raising=False)
    return monkeypatch


def test_gate_ativo_desligado_sem_variavel(ambiente_limpo):
    assert gates.active_probes_authorized() is False


@pytest.mark.parametrize("valor", ["", "0", "true", "True", "yes", "sim", "2", " 1", "1 "])
def test_so_o_valor_exato_1_libera(ambiente_limpo, valor):
    """Nenhum caminho liga por default, e nenhum quase-verdadeiro liga.

    `"true"` e `" 1"` são o tipo de valor que entra num compose por descuido. A
    comparação exata é a diferença entre autorização e acidente.
    """
    ambiente_limpo.setenv(gates.ACTIVE_PROBES_ENV, valor)
    assert gates.active_probes_authorized() is False, f"{valor!r} não pode autorizar"


def test_valor_1_libera(ambiente_limpo):
    ambiente_limpo.setenv(gates.ACTIVE_PROBES_ENV, "1")
    assert gates.active_probes_authorized() is True


def test_require_active_probes_pula_sem_autorizacao(ambiente_limpo):
    """Skip, não fail: ausência de autorização não é defeito do alvo."""
    with pytest.raises(pytest.skip.Exception, match=gates.ACTIVE_PROBES_ENV):
        gates.require_active_probes()


def test_require_active_probes_deixa_passar_com_autorizacao(ambiente_limpo):
    ambiente_limpo.setenv(gates.ACTIVE_PROBES_ENV, "1")
    gates.require_active_probes()      # não levanta: é a única forma de passar


def test_a_mensagem_do_gate_diz_o_que_fazer_e_por_que(ambiente_limpo):
    """Gate que barra sem explicar vira variável exportada às cegas."""
    with pytest.raises(pytest.skip.Exception) as erro:
        gates.require_active_probes()
    mensagem = str(erro.value)
    assert gates.ACTIVE_PROBES_ENV in mensagem
    assert "autoriza" in mensagem.lower()


# ---------- os dois gates são independentes (matriz 2×2) ----------

@pytest.mark.parametrize("carga,sondagem", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_matriz_dos_dois_gates(ambiente_limpo, carga, sondagem):
    """Autorizar carga NUNCA autoriza sondagem, e vice-versa.

    São intrusões de natureza diferente: carga arrisca a disponibilidade do
    alvo; sondagem pergunta ao servidor o que ele não ofereceu. Quem autoriza
    uma não está autorizando a outra, e misturar as duas seria assumir um
    consentimento que ninguém deu.
    """
    if carga:
        ambiente_limpo.setenv(gates.LOAD_ENV, "1")
    if sondagem:
        ambiente_limpo.setenv(gates.ACTIVE_PROBES_ENV, "1")

    assert gates.load_authorized() is carga
    assert gates.active_probes_authorized() is sondagem


def test_gate_de_carga_nao_vaza_para_sondagem(ambiente_limpo):
    """O caso que mais importa da matriz, isolado para não passar despercebido."""
    ambiente_limpo.setenv(gates.LOAD_ENV, "1")
    assert gates.active_probes_authorized() is False
    with pytest.raises(pytest.skip.Exception):
        gates.require_active_probes()


def test_gate_de_llm_tambem_e_independente(ambiente_limpo):
    """Terceiro gate, mesma regra: ligar IA não autoriza tocar no alvo."""
    ambiente_limpo.setenv(gates.LLM_ENV, "1")
    assert gates.active_probes_authorized() is False
    assert gates.load_authorized() is False


# ---------- nenhum gate é consumido por acidente ----------

def test_nenhum_check_consome_o_gate_ativo_hoje():
    """O gate nasceu ANTES do primeiro teste ativo, de propósito: guarda criada
    junto com a funcionalidade nasce frouxa. Enquanto a Fase C não existir,
    ninguém deve chamá-lo — e se alguém chamar, é sinal de que começou."""
    consumidores = [
        str(a.relative_to(RAIZ)) for a in sorted(CHECKS.rglob("*.py"))
        if "require_active_probes" in a.read_text(encoding="utf-8")
    ]
    assert consumidores == [], (
        f"{consumidores} consomem o gate de sondagem ativa. Se a Fase C começou, "
        "este teste precisa mudar junto — de propósito, num PR que diga isso.")


def test_o_ambiente_de_teste_nao_traz_autorizacao_ligada():
    """Guarda contra o pior cenário operacional: alguém exporta a variável no
    shell e a suíte inteira roda autorizada sem ninguém notar."""
    assert os.environ.get(gates.ACTIVE_PROBES_ENV) != "1", (
        f"{gates.ACTIVE_PROBES_ENV}=1 está no ambiente desta execução. "
        "A Fase C está travada; nada deveria autorizá-la aqui.")
