"""VERIFICAÇÃO: o ciclo da linha de base e a borda de evidência (R19).

Dois assuntos, e os dois têm modo de falha silencioso:

* **a linha de base** — referência ausente que "passa" anuncia estabilidade que
  ninguém mediu, e manifesto velho descrevendo imagem nova é uma procedência que
  mente. Nenhum dos dois estoura sozinho;
* **a borda de pixel** — `webqa/sanitize.py` mascara texto e não alcança PNG.
  Uma captura de aplicação real exibe o que estiver na tela, e a mitigação
  registrada para o R19 é NÃO COLETAR. O molde da guarda é o mesmo de
  `tests/test_vazamento_de_credencial.py`: não basta a intenção estar no código,
  é preciso provar que nenhum arquivo aparece.
"""
from __future__ import annotations

import json

import pytest

from webqa.evidencias import (
    ENV_CAPTURAS,
    alvo_fabricado,
    capturas_autorizadas,
    motivo_de_nao_gravar,
    pode_gravar_png,
)
from webqa.referencia_visual import (
    CAMPOS_DO_MANIFESTO,
    Artefato,
    carregar_paginas,
    diretorio,
    existe,
    gravar,
    motivo_de_pular,
    problemas_do_manifesto,
)

pytestmark = pytest.mark.verification

PNG_FAKE = b"\x89PNG\r\n\x1a\n" + b"conteudo de mentira, mas com sha proprio"
ARTEFATO = Artefato(pagina="/gui/visual", viewport="desktop")


# ---------- O ciclo: skip → grava → passa → muda → reprova ----------

def test_sem_referencia_o_motivo_manda_gravar(tmp_path):
    """Nunca PASS. No primeiro run não há o que comparar, e passar aí anunciaria
    estabilidade que ninguém mediu — o verde indistinguível do legítimo."""
    assert not existe(ARTEFATO, tmp_path)
    motivo = motivo_de_pular(ARTEFATO, tmp_path)
    assert "make referencia-visual" in motivo
    assert "/gui/visual|desktop|light" in motivo


def test_gravar_escreve_png_E_manifesto_juntos(tmp_path):
    """Não há caminho neste módulo que grave só um: PNG sem manifesto é uma
    referência de origem desconhecida, e ninguém ousa regravá-la depois."""
    gravar(ARTEFATO, PNG_FAKE, engine="chromium", gravado_em="2026-01-01 00:00:00 UTC",
           motivo="teste", base=tmp_path)
    assert existe(ARTEFATO, tmp_path)
    assert problemas_do_manifesto(ARTEFATO, tmp_path) == []


def test_png_regravado_sem_manifesto_novo_REPROVA(tmp_path):
    """O mecanismo é o `sha256`: o manifesto descreve UM arquivo.

    É o caso que a regra da OS cobra — regravação sem manifesto atualizado
    reprova. Sem isso, uma referência trocada à mão passaria a valer com a
    procedência de outra imagem.
    """
    gravar(ARTEFATO, PNG_FAKE, engine="chromium", gravado_em="2026-01-01 00:00:00 UTC",
           motivo="teste", base=tmp_path)
    (tmp_path / f"{ARTEFATO.nome}.png").write_bytes(PNG_FAKE + b"mudou")

    problemas = problemas_do_manifesto(ARTEFATO, tmp_path)
    assert any("o PNG mudou e o manifesto não" in p for p in problemas)
    assert any("make referencia-visual" in p for p in problemas)


def test_manifesto_ausente_reprova(tmp_path):
    (tmp_path / f"{ARTEFATO.nome}.png").write_bytes(PNG_FAKE)
    assert any("manifesto ausente" in p for p in problemas_do_manifesto(ARTEFATO, tmp_path))


@pytest.mark.parametrize("campo", CAMPOS_DO_MANIFESTO)
def test_todo_campo_da_procedencia_e_obrigatorio(campo, tmp_path):
    """`motivo` inclusive: referência sem explicação é indistinguível de
    referência esquecida — e é justamente a que ninguém ousa regravar."""
    gravar(ARTEFATO, PNG_FAKE, engine="chromium", gravado_em="2026-01-01 00:00:00 UTC",
           motivo="teste", base=tmp_path)
    caminho = tmp_path / f"{ARTEFATO.nome}.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados[campo] = ""
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    assert any(campo in p for p in problemas_do_manifesto(ARTEFATO, tmp_path))


def test_identidade_separa_viewport_e_tema(tmp_path):
    """Sem os três no nome, a referência de `mobile` acaba comparada com a
    captura de `desktop` e o diff acusa a página inteira — com a causa escondida
    atrás de "94% dos blocos divergentes"."""
    movel = Artefato(pagina="/gui/visual", viewport="mobile")
    escuro = Artefato(pagina="/gui/visual", viewport="desktop", tema="dark")
    nomes = {ARTEFATO.nome, movel.nome, escuro.nome}
    assert len(nomes) == 3
    gravar(ARTEFATO, PNG_FAKE, engine="chromium", gravado_em="x", motivo="y", base=tmp_path)
    assert not existe(movel, tmp_path) and not existe(escuro, tmp_path)


def test_componente_tem_artefato_proprio():
    paginas = carregar_paginas()
    com_componentes = [p for p in paginas if p.componentes]
    assert com_componentes, "o contrato visual declara componentes para o GUI-VIS-02"
    visual = com_componentes[0]
    assert visual.artefato().nome != visual.artefato(visual.componentes[0]).nome


# ---------- O contrato visual está LIGADO ----------

def test_as_paginas_do_contrato_visual_vem_do_yaml():
    """Chave que ninguém lê é "a garantia existe, a ligação não"."""
    paginas = carregar_paginas()
    caminhos = {p.caminho for p in paginas}
    assert "/gui/visual" in caminhos and "/gui/visual-mudado" in caminhos


def test_a_pagina_deslocada_NAO_e_regravavel():
    """É o que mantém a direção `failed` viva.

    `make referencia-visual` regravaria a referência defasada, o deslocamento
    deixaria de divergir, e o check nunca mais reprovaria — o contrato visual
    passaria a ter só a direção que passa, que é a mesma coisa que não ter
    contrato nenhum.
    """
    deslocada = next(p for p in carregar_paginas() if p.caminho == "/gui/visual-mudado")
    assert not deslocada.regravar


def test_a_referencia_defasada_declara_no_manifesto_que_e_defasada():
    """Uma referência que diverge de propósito PRECISA dizer isso, senão o
    próximo executor a "conserta" achando que achou um bug."""
    artefato = Artefato(pagina="/gui/visual-mudado", viewport="desktop")
    from webqa.referencia_visual import ler_manifesto
    motivo = (ler_manifesto(artefato) or {}).get("motivo", "")
    assert "DELIBERADAMENTE DEFASADA" in motivo
    assert "regravar" in motivo.lower()


def test_referencia_versionada_vive_no_alvo_fabricado():
    """`report/` nunca é versionado e captura de alvo real não é versionável
    (R19). A única via que cabe no Git é a do alvo fabricado."""
    assert diretorio({}).name == "baseline"
    assert diretorio({}).parent.name == "fixture_target"


def test_diretorio_externo_e_respeitado():
    assert diretorio({"WEBQA_GUI_BASELINE_DIR": "/tmp/base"}).as_posix() == "/tmp/base"


# ---------- A borda de evidência (R19) ----------

def test_so_a_string_exata_1_autoriza_captura():
    """Fail-closed, no molde de `webqa/gates.py`: um valor quase-certo numa
    variável de ambiente não pode ser lido como consentimento."""
    assert capturas_autorizadas({ENV_CAPTURAS: "1"})
    for valor in ("true", "yes", " 1", "0", ""):
        assert not capturas_autorizadas({ENV_CAPTURAS: valor}), valor
    assert not capturas_autorizadas({})


def test_alvo_fabricado_e_reconhecido_e_alvo_real_nao():
    assert alvo_fabricado("http://127.0.0.1:8000/")
    assert not alvo_fabricado("https://example.com/")
    assert not alvo_fabricado("")


def test_sem_optin_alvo_real_NAO_pode_gravar_png():
    """A mitigação registrada para o R19 é NÃO COLETAR, e o default é esse."""
    assert not pode_gravar_png("https://example.com/", {})
    assert pode_gravar_png("https://example.com/", {ENV_CAPTURAS: "1"})
    assert pode_gravar_png("http://127.0.0.1:9000/", {}), "o fabricado é a exceção"


def test_o_motivo_de_nao_gravar_explica_a_omissao():
    """Ausência silenciosa de artefato é indistinguível de artefato perdido."""
    motivo = motivo_de_nao_gravar("https://example.com/painel")
    assert ENV_CAPTURAS in motivo and "R19" in motivo
    assert "dado de quem estava logado" in motivo


# ---------- A prova de que NENHUM png escapa (molde de test_vazamento_de_credencial) ----------

def test_nenhum_check_grava_png_em_disco():
    """**Prova estrutural, e é a que continua valendo amanhã.**

    Um PNG só chega ao disco por `screenshot(path=...)` ou por `gravar(...)`.
    Nenhum dos dois pode aparecer em `checks/`: a captura dos checks fica em
    MEMÓRIA, e o único caminho que escreve é `scripts/referencia_visual.py`, que
    roda contra `AlvoFixture` e mais nada.

    A prova é no fonte porque a comportamental só cobre o caminho de hoje — e o
    risco aqui é o próximo check, escrito daqui a um ano por alguém que quer "só
    depurar" e grava a tela de um alvo real com dado de quem estava logado.
    """
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    ofensores = []
    for arquivo in sorted((raiz / "checks").rglob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        # Só CÓDIGO: docstring e comentário explicam a regra e não a violam.
        codigo = "\n".join(linha.split("#", 1)[0] for linha in fonte.splitlines())
        if "screenshot(path" in codigo or "path=" in codigo and "screenshot" in codigo:
            ofensores.append(f"{arquivo.name}: screenshot com path")
        if "referencia_visual import" in codigo and "gravar" in codigo.split("import", 1)[-1][:200]:
            ofensores.append(f"{arquivo.name}: importa gravar()")
    assert not ofensores, (
        "check gravando PNG em disco: " + "; ".join(ofensores)
        + ". Pixel não passa pela borda de sanitização (R19) e tela de aplicação "
          "real exibe dado de quem estava logado. O caminho que grava é "
          "`make referencia-visual`, contra o alvo fabricado.")


def test_o_script_de_regravacao_so_aponta_para_o_alvo_fabricado():
    """Não há opção de apontar a regravação para um site real — e não pode
    haver: a referência versionada vive no Git."""
    from pathlib import Path
    fonte = (Path(__file__).resolve().parent.parent
             / "scripts" / "referencia_visual.py").read_text(encoding="utf-8")
    assert "AlvoFixture" in fonte
    assert "WEBQA_TARGET_URL" not in fonte, (
        "o script não pode aceitar alvo externo: captura de alvo real não é "
        "versionável (R19)")
