"""VERIFICAÇÃO de que a Fase C só existe sob gate + escopo + auditoria (PR-C0d).

INVERSÃO da trava (OS-36 → C0d), aplicada com sign-off escrito de code owner
(@danzeroum, 2026-08-02). Antes, este arquivo provava a **ausência** da
capacidade: nenhum símbolo de sondagem ativa podia existir. Agora ele prova o
**contorno**: a capacidade PODE existir, mas só sob governança — todo módulo de
`webqa/` que defina sondagem ativa consome `require_discovery` +
`require_escopo` e registra em auditoria (`AuditLog`); `checks/` (camada passiva)
não define sondagem alguma. Enquanto o motor (C1, `webqa/sondagem.py`) não for
escrito, nenhum módulo define os símbolos e a verificação passa: a trava abriu,
o motor virá.

O que NÃO mudou, e por quê: os gates continuam fail-closed (só `"1"` autoriza),
independentes entre si, e `require_active_probes` continua pulando sem
autorização; a camada passiva não sonda caminho não oferecido nem consome o gate
ativo; e o ambiente de teste continua proibido de rodar autorizado. Abrir a
trava move a fronteira de "não existe" para "existe gated" — não afrouxa nenhuma
garantia estrutural. E abrir a trava NÃO autoriza sondar alvo nenhum: isso ainda
exige escopo + prova de posse (webqa/escopo.py).

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


# Onde o motor de C1 (sondagem ativa) viveria: na BIBLIOTECA, nunca em checks/
# (a camada passiva de testes). Marcas de que um módulo passa pelos portões.
BIBLIOTECA = RAIZ / "webqa"
_MARCAS_DE_GOVERNANCA = ("require_discovery", "require_escopo")
_MARCA_DE_AUDITORIA = "AuditLog"


def _define_sondagem(arvore: ast.AST) -> bool:
    """O módulo define algum símbolo de sondagem ativa?"""
    return any(
        isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and no.name in SIMBOLOS_DA_FASE_C
        for no in ast.walk(arvore))


def test_sondagem_ativa_so_existe_sob_gate_escopo_e_auditoria():
    """INVERSÃO de `test_fase_c_nao_existe_ainda` (PR-C0d).

    Antes: nenhum símbolo de sondagem podia existir. Agora que a trava abriu, a
    capacidade PODE existir — mas só sob governança. Todo módulo de `webqa/` que
    DEFINA um símbolo de sondagem tem de consumir `require_discovery` +
    `require_escopo` e registrar em `AuditLog`; e `checks/` (passiva) não define
    sondagem alguma, gated ou não. Se a Fase C ainda não foi construída, nenhum
    módulo define os símbolos e o teste passa: a trava abriu, o motor virá em C1.

    Reprova exatamente o que a inversão precisa reprovar: capacidade de sondagem
    sem gate/escopo — o probe que "é só um GET" entrando sem autorização.
    """
    ofensores = []
    # checks/ é passiva: NENHUM símbolo de sondagem pode ser definido lá.
    for arquivo in sorted(CHECKS.rglob("*.py")):
        if _define_sondagem(ast.parse(arquivo.read_text(encoding="utf-8"))):
            ofensores.append(f"{arquivo.relative_to(RAIZ)}: sondagem em checks/ "
                             "(camada passiva) — o motor de C1 vive em webqa/")
    # webqa/: a capacidade PODE existir, mas só sob gate + escopo + auditoria.
    for arquivo in sorted(BIBLIOTECA.rglob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        if not _define_sondagem(ast.parse(fonte)):
            continue
        faltando = [m for m in _MARCAS_DE_GOVERNANCA if m not in fonte]
        if _MARCA_DE_AUDITORIA not in fonte:
            faltando.append(_MARCA_DE_AUDITORIA)
        if faltando:
            ofensores.append(f"{arquivo.relative_to(RAIZ)} define sondagem sem: "
                             + ", ".join(faltando))

    assert not ofensores, (
        "capacidade de sondagem ativa fora da governança de C1:\n  "
        + "\n  ".join(ofensores)
        + "\nTodo módulo de sondagem exige require_discovery + require_escopo + "
          "AuditLog, e nunca vive em checks/. Ver PR-C0d e docs/FASE-C.md.")


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
    """A camada passiva (`checks/`) não consome o gate de sondagem ativa — nem
    agora que a trava abriu. O consumo legítimo mora no motor de C1
    (`webqa/sondagem.py`), fora de `checks/`; um check que passe a chamá-lo
    deixou de ser passivo, e isso precisa de um PR que diga isso."""
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
