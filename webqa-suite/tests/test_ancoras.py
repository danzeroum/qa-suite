"""VERIFICAÇÃO: a guarda de âncoras `arquivo:linha` pega o que existe para pegar.

Quatro perguntas, na ordem do risco:

1. **o parser reconhece as formas que a casa usa?** `N`, `N-M`, `N,M`, caminho
   relativo a raízes implícitas, e a âncora relativa (`` `:30-35` ``) com e sem
   parênteses. Forma não reconhecida some da conferência **em silêncio**, e uma
   guarda que perde caso calada é pior que guarda nenhuma: ela produz o verde que
   dispensa a conferência manual;
2. **os dois lados da bidirecional reprovam?** Provado por MUTAÇÃO: âncora
   deslocada plantada reprova por um lado, entrada órfã plantada reprova pelo
   outro. Guarda que nunca reprovou nada é decoração;
3. **cobertura declarada é obrigatória?** Documento sem estado reprova, e
   pendente conta sem reprovar;
4. **a tranche 1 está de fato verde?** É o teste de ACEITAÇÃO desta OS, e roda
   contra os documentos reais — não contra prosa fabricada.
"""
import pytest
import yaml

from scripts.afere_ancoras import (
    aferir,
    ancoras_de,
    carregar,
    documentos_do_repo,
    linhas_de,
    problemas_de_cobertura,
    problemas_do_documento,
    resolver_caminho,
    resumo,
)

pytestmark = pytest.mark.verification

TRANCHE_1 = (
    "webqa-suite/docs/GUI.md",
    "webqa-suite/docs/GUI-CATALOGO.md",
    "webqa-suite/docs/handoff/ordens-de-servico/OS-gui-fila.md",
    "webqa-suite/docs/PROXIMOS-PASSOS.md",
)


@pytest.fixture()
def repo(tmp_path):
    """Um repositório de mentira: um alvo com conteúdo conhecido e um doc."""
    (tmp_path / "alvo.py").write_text(
        "\n".join(f"linha {n}" if n != 7 else "def marco_distintivo():"
                  for n in range(1, 21)) + "\n", encoding="utf-8")
    return tmp_path


def _doc(repo, texto):
    (repo / "doc.md").write_text(texto, encoding="utf-8")
    return "doc.md"


# ---------- 1. o parser ----------

def test_linhas_de_cobre_as_tres_formas():
    assert linhas_de("56") == (56,)
    assert linhas_de("10-13") == (10, 11, 12, 13)
    assert linhas_de("72,80") == (72, 80)
    assert linhas_de("36-38,45-47") == (36, 37, 38, 45, 46, 47)


def test_parser_reconhece_numero_intervalo_e_lista(repo):
    texto = "veja `alvo.py:7`, `alvo.py:5-8` e `alvo.py:7,9`."
    chaves = {a.chave for a in ancoras_de(texto, repo)}
    assert chaves == {"alvo.py:7", "alvo.py:5-8", "alvo.py:7,9"}


def test_caminho_inexistente_e_ignorado_e_nao_reprova(repo):
    """Prosa que PARECE caminho (`app.js:12` num exemplo) não é âncora. Cobrar
    documentação por texto que não aponta para nada tornaria a guarda um
    estorvo, e guarda-estorvo é desligada."""
    assert ancoras_de("exemplo: `nao_existe.py:3`", repo) == ()


def test_caminho_resolve_contra_raizes_implicitas():
    """`ARQUITETURA.md:44` (de `docs/`) e `report_html.py:382` (de `webqa/`) são
    âncoras legítimas para quem lê. Tratá-las como inexistentes deixaria 21 das
    91 âncoras da tranche 1 fora da conferência, com a guarda parecendo
    completa."""
    assert resolver_caminho("ARQUITETURA.md") == "webqa-suite/docs/ARQUITETURA.md"
    assert resolver_caminho("report_html.py") == "webqa-suite/webqa/report_html.py"
    assert resolver_caminho("lgpd/test_terceiros.py") == "webqa-suite/checks/lgpd/test_terceiros.py"
    assert resolver_caminho("nada_disso_existe.py") is None


def test_ancora_relativa_herda_o_caminho_anterior(repo):
    texto = "o módulo `alvo.py` faz o que faz (`:7`) e mais isso `:5-8`."
    ancoras = ancoras_de(texto, repo)
    assert [a.chave for a in ancoras] == ["alvo.py:7", "alvo.py:5-8"]
    assert all(a.relativa for a in ancoras), "as duas são relativas"


def test_relativa_sem_caminho_antes_e_ignorada(repo):
    """Não há o que herdar, e adivinhar seria pior que omitir."""
    assert ancoras_de("solta no vazio: `:7`", repo) == ()


def test_dois_pontos_sem_caminho_nao_e_ancora(repo):
    """`1:1` num título ("O contrato do alvo fixture é 1:1") não é âncora — e é
    caso real do PROXIMOS-PASSOS.md, o único `:N` daquele documento."""
    assert ancoras_de("### 2.8 O contrato do alvo fixture é 1:1", repo) == ()


# ---------- 2. os dois lados, por mutação ----------

def test_ancora_verdadeira_nao_reprova(repo):
    doc = _doc(repo, "veja `alvo.py:7`.")
    assert problemas_do_documento(doc, {"alvo.py:7": "def marco_distintivo"}, repo) == []


def test_ancora_deslocada_reprova(repo):
    """MUTAÇÃO, lado 1: o alvo se moveu e o documento não. É o defeito que a
    OS-48 e a OS-50 produziram, duas vezes, com fixture nova no conftest."""
    doc = _doc(repo, "veja `alvo.py:3`.")
    problemas = problemas_do_documento(doc, {"alvo.py:3": "def marco_distintivo"}, repo)
    assert len(problemas) == 1
    assert "def marco_distintivo" in problemas[0], "o erro precisa dizer o que procurar"
    assert "doc.md" in problemas[0], "e qual documento consertar"


def test_ancora_fora_do_mapa_reprova(repo):
    """MUTAÇÃO, lado 2a: âncora nova entrando sem passar por conferência."""
    doc = _doc(repo, "veja `alvo.py:7` e também `alvo.py:9`.")
    problemas = problemas_do_documento(doc, {"alvo.py:7": "def marco_distintivo"}, repo)
    assert len(problemas) == 1 and "alvo.py:9" in problemas[0]


def test_entrada_orfa_no_mapa_reprova(repo):
    """MUTAÇÃO, lado 2b: âncora removida do doc deixando entrada que finge
    cobertura. Sem este lado o mapa incha e o placar mente para cima."""
    doc = _doc(repo, "veja `alvo.py:7`.")
    problemas = problemas_do_documento(
        doc, {"alvo.py:7": "def marco_distintivo", "alvo.py:12": "linha 12"}, repo)
    assert len(problemas) == 1 and "alvo.py:12" in problemas[0]


def test_intervalo_alem_do_fim_do_arquivo_reprova(repo):
    """Caso real da tranche 1: `test_acessibilidade.py:72,80` num arquivo de 75
    linhas. Aqui o erro é outro — não "aponta para outra coisa", e sim "aponta
    para lugar nenhum" — e a mensagem precisa dizer isso."""
    doc = _doc(repo, "veja `alvo.py:19-25`.")
    problemas = problemas_do_documento(doc, {"alvo.py:19-25": "linha 19"}, repo)
    assert len(problemas) == 1
    assert "passa do fim do arquivo" in problemas[0]
    assert "20 linhas" in problemas[0], "diga QUANTAS linhas o arquivo tem"


# ---------- 3. cobertura declarada ----------

def test_documento_sem_estado_declarado_reprova():
    """Doc novo não pode nascer invisível à guarda — é assim que uma cobertura
    parcial passa por completa."""
    problemas = problemas_de_cobertura({}, ["docs/NOVO.md"])
    assert len(problemas) == 1 and "NOVO.md" in problemas[0]


def test_estado_invalido_reprova():
    problemas = problemas_de_cobertura({"d.md": {"estado": "quase"}}, [])
    assert any("quase" in p for p in problemas)


def test_pendente_sem_motivo_reprova():
    """Estado sem motivo é decisão que ninguém consegue revisar depois."""
    problemas = problemas_de_cobertura({"d.md": {"estado": "pendente"}}, [])
    assert any("sem motivo" in p for p in problemas)


def test_pendente_com_motivo_conta_e_nao_reprova(repo, monkeypatch):
    declarados = {"d.md": {"estado": "pendente", "motivo": "entra na tranche 2"}}
    problemas, placar = aferir(declarados, repo)
    assert problemas == [], "pendente declarado não é defeito — é dívida visível"
    assert placar["pendentes"] == ["d.md"]
    assert "1 pendente(s)" in resumo(placar)


def test_o_placar_sai_mesmo_sem_problema_nenhum(repo):
    """Pendente silencioso é o modo de falha desta guarda: o verde seria lido
    como "a documentação está conferida"."""
    _, placar = aferir({}, repo)
    assert "pendente(s)" in resumo(placar) and "auditado(s)" in resumo(placar)


# ---------- 4. aceitação: a tranche 1 de verdade ----------

def test_todo_documento_do_repo_tem_estado_declarado():
    problemas = problemas_de_cobertura(carregar(), documentos_do_repo())
    assert problemas == [], "\n".join(problemas)


@pytest.mark.parametrize("doc", TRANCHE_1)
def test_tranche_1_esta_auditada(doc):
    declarado = carregar().get(doc, {})
    assert declarado.get("estado") == "auditado", f"{doc} saiu da tranche 1"


@pytest.mark.parametrize("doc", TRANCHE_1)
def test_tranche_1_sem_ancora_fora_do_mapa_nem_orfa(doc):
    """A ACEITAÇÃO da OS-57: zero âncoras fora do mapa, zero órfãs, zero
    apontando para outra coisa — nos quatro documentos, de verdade."""
    mapa = carregar()[doc].get("ancoras") or {}
    problemas = problemas_do_documento(doc, mapa, None)
    assert problemas == [], "\n".join(problemas)


def test_a_guarda_inteira_esta_verde():
    problemas, placar = aferir(carregar())
    assert problemas == [], "\n".join(problemas)
    assert placar["ancoras"] >= 85, (
        f"o mapa encolheu para {placar['ancoras']} âncoras — se foi de propósito, "
        "baixe este piso no mesmo commit e diga por quê")


def test_congelados_do_handoff_declarados_com_motivo():
    declarados = carregar()
    for doc in ("webqa-suite/docs/handoff/LEIA-PRIMEIRO.md",
                "webqa-suite/docs/handoff/ordens-de-servico/OS-abertas.md"):
        assert declarados[doc]["estado"] == "congelado"
        assert declarados[doc]["motivo"].strip()


def test_o_yaml_e_yaml_valido_e_tem_a_chave_de_topo():
    from scripts.afere_ancoras import MAPA_PADRAO
    dados = yaml.safe_load(MAPA_PADRAO.read_text(encoding="utf-8"))
    assert "documentos" in dados
