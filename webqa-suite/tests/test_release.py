"""VERIFICAÇÃO da release ancorável (frente E, E2).

O que a E1 fechou foi o caminho até o pacote; o que esta trava é o que "versão"
significa. `webqa-suite==1.0.0` e `auditar.yml@v1.0.0` só valem alguma coisa se
houver uma âncora que **não seja a própria tag** — tag é ponteiro móvel, e
ponteiro móvel não ancora nada.

Três famílias, e cada uma pega um defeito diferente:

* **a forma do manifesto** — sobre dados fabricados, inclusive as bordas que não
  dá para produzir no repositório real (`reprovada` não representável, pendência
  sem motivo, digest malformado);
* **o manifesto REAL desta árvore** — o que está em `releases/` descreve o que
  diz descrever;
* **a disciplina de versão** — cortada a tag, `main` tem de sair daquele número.
  Enquanto não sair, dois conteúdos distintos reivindicam a mesma versão e a
  comparabilidade que a versão existe para dar deixa de valer sem nada ficar
  vermelho. É o teste que reprova o PR seguinte a um bump esquecido.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.publicar_release import (
    ESTADOS_DE_MORDIDA,
    digerir_catalogo,
    problemas_de_forma,
)

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent
DIR_RELEASES = RAIZ / "releases"


def manifesto_valido(**mudancas) -> dict:
    base = {
        "schema_version": "1.0",
        "repositorio": "danzeroum/qa-suite",
        "tag": "v1.0.0",
        "versao": "1.0.0",
        "commit_sha": "a" * 40,
        "tree_digest": "sha256:" + "b" * 64,
        "catalogo": {"caminhos_sensiveis_hash": "sha256:" + "c" * 64,
                     "checks_hash": "sha256:" + "d" * 64},
        "mordida": {"estado": "pendente", "motivo": "a autoprova é a entrega 5"},
    }
    base.update(mudancas)
    return base


def releases_publicadas() -> list[dict]:
    """Todo manifesto em `releases/`, lido do disco."""
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(DIR_RELEASES.glob("v*.manifesto.json"))]


# ---------- A forma do manifesto ----------

def test_manifesto_bem_formado_nao_tem_problema():
    assert problemas_de_forma(manifesto_valido()) == []


@pytest.mark.parametrize("campo", ["tag", "versao", "commit_sha", "tree_digest",
                                   "catalogo", "mordida", "repositorio", "schema_version"])
def test_campo_ausente_reprova(campo):
    """Manifesto incompleto é ausência de âncora, não âncora aproximada."""
    m = manifesto_valido()
    del m[campo]
    assert any(campo in p for p in problemas_de_forma(m))


def test_tag_que_nao_casa_com_a_versao_reprova():
    """A tag é o nome público da versão; divergirem faz o consumidor pinar outra coisa."""
    assert problemas_de_forma(manifesto_valido(tag="v9.9.9"))


def test_versao_de_desenvolvimento_nao_vira_release():
    """`.dev` não é release: a tag existe para ancorar o que alguém instala e compara."""
    problemas = problemas_de_forma(manifesto_valido(versao="1.1.0.dev0", tag="v1.1.0.dev0"))
    assert any("X.Y.Z" in p for p in problemas)


def test_mordida_reprovada_nao_e_representavel():
    """A categoria "release publicada com autoprova vermelha", existindo, seria usada."""
    assert "reprovada" not in ESTADOS_DE_MORDIDA
    problemas = problemas_de_forma(manifesto_valido(mordida={"estado": "reprovada"}))
    assert any("reprovada" in p for p in problemas)


def test_mordida_pendente_sem_motivo_reprova():
    """Pendência sem motivo é uma decisão que ninguém consegue revisar depois."""
    problemas = problemas_de_forma(manifesto_valido(mordida={"estado": "pendente"}))
    assert any("motivo" in p for p in problemas)


def test_mordida_aprovada_dispensa_motivo_mas_exige_numeros():
    """O outro lado: exigir MOTIVO do estado bom transformaria a guarda em ritual.

    A exigência mudou na E5, e mudou porque a autoprova passou a existir: `aprovada`
    sem contagem seria um selo — quem lê o manifesto veria a palavra e não teria
    como perguntar *aprovada em quê*. O motivo segue dispensado; os números, não.
    """
    aprovada = {"estado": "aprovada", "devem_falhar": "28/28", "smoke_gui": "4/4",
                "declarado_sem_mordida": 15}
    assert problemas_de_forma(manifesto_valido(mordida=aprovada)) == []
    assert "motivo" not in aprovada


@pytest.mark.parametrize("chave", ["caminhos_sensiveis_hash", "checks_hash"])
def test_digest_malformado_no_catalogo_reprova(chave):
    m = manifesto_valido()
    m["catalogo"][chave] = "nao-e-digest"
    assert any(chave in p for p in problemas_de_forma(m))


# ---------- O digest do catálogo ----------

def test_o_digest_do_catalogo_ignora_a_populacao_suite():
    """`tests/` verifica a SUÍTE; não julga alvo.

    Se entrasse no digest, cada teste novo da própria suíte mudaria o catálogo — e
    o consumidor veria "a régua mudou" numa alteração que não muda nada do que a
    régua mede. Guarda que grita por qualquer coisa é desligada.
    """
    so_alvo = {"testes": [{"nodeid": "checks/x.py::a", "populacao": "alvo", "dimensoes": ["gui"]}]}
    com_suite = {"testes": [*so_alvo["testes"],
                            {"nodeid": "tests/y.py::b", "populacao": "suite", "dimensoes": []}]}
    assert digerir_catalogo(so_alvo) == digerir_catalogo(com_suite)


def test_o_digest_do_catalogo_muda_quando_um_check_entra():
    """E o outro sentido: superfície de julgamento diferente TEM de aparecer."""
    antes = {"testes": [{"nodeid": "checks/x.py::a", "populacao": "alvo", "dimensoes": ["gui"]}]}
    depois = {"testes": [*antes["testes"],
                         {"nodeid": "checks/x.py::b", "populacao": "alvo", "dimensoes": ["gui"]}]}
    assert digerir_catalogo(antes) != digerir_catalogo(depois)


def test_o_digest_do_catalogo_muda_quando_a_dimensao_muda():
    """Mesmo check, outra dimensão: o laudo passa a contá-lo em outra coluna."""
    a = {"testes": [{"nodeid": "checks/x.py::a", "populacao": "alvo", "dimensoes": ["gui"]}]}
    b = {"testes": [{"nodeid": "checks/x.py::a", "populacao": "alvo", "dimensoes": ["ux"]}]}
    assert digerir_catalogo(a) != digerir_catalogo(b)


def test_o_digest_do_catalogo_nao_depende_da_ordem_da_coleta():
    """A ordem em que o coletor percorre o disco não é propriedade da régua."""
    testes = [{"nodeid": "checks/b.py::z", "populacao": "alvo", "dimensoes": ["ux", "lgpd"]},
              {"nodeid": "checks/a.py::y", "populacao": "alvo", "dimensoes": ["gui"]}]
    assert digerir_catalogo({"testes": testes}) == digerir_catalogo({"testes": testes[::-1]})


# ---------- O que está publicado nesta árvore ----------

def test_ha_pelo_menos_uma_release_publicada():
    """`releases/` vazio significaria que a E2 não aconteceu."""
    assert releases_publicadas(), (
        "nenhum manifesto em releases/. Sem release ancorável, o consumidor pina uma tag e não "
        "tem digest para guardar — 'continua sendo o que eu instalei' volta a ser indemonstrável.")


@pytest.mark.parametrize("manifesto", releases_publicadas(),
                         ids=lambda m: m.get("tag", "?"))
def test_manifesto_publicado_esta_bem_formado(manifesto):
    assert problemas_de_forma(manifesto) == []


@pytest.mark.parametrize("manifesto", releases_publicadas(),
                         ids=lambda m: m.get("tag", "?"))
def test_o_nome_do_arquivo_casa_com_a_tag_declarada(manifesto):
    """Dois manifestos podendo se referir à mesma release é ambiguidade, não redundância."""
    assert (DIR_RELEASES / f"{manifesto['tag']}.manifesto.json").exists()


# ---------- Disciplina de versão ----------

def ultima_release() -> dict:
    """A release de maior versão publicada — a que o README manda instalar."""
    def chave(m):
        return tuple(int(x) for x in m["versao"].split("."))
    return max(releases_publicadas(), key=chave)


def test_a_ponta_nao_reivindica_a_versao_ja_publicada():
    """O teste de disciplina de versão, e é ele que reprova o bump esquecido.

    Cortada a tag `vX.Y.Z`, `main` PRECISA sair de `X.Y.Z`. Enquanto não sair, dois
    conteúdos diferentes — o taggeado e a ponta, que já andou — dizem ter a mesma
    versão. Como a versão do wheel é dinâmica, os dois produzem artefatos com o
    mesmo número, e a comparabilidade de laudos que a versão existe para dar deixa
    de valer sem nada ficar vermelho.
    """
    from webqa import __version__

    publicada = ultima_release()["versao"]
    assert __version__ != publicada, (
        f"__version__ da ponta é {__version__!r}, igual à release {publicada!r} já publicada. "
        f"Bumpe para a próxima dev/minor: enquanto os dois forem iguais, dois conteúdos "
        f"distintos reivindicam a mesma régua.")


def test_a_ponta_esta_a_frente_da_ultima_release():
    """Sair da versão publicada não basta: sair para TRÁS seria pior que não sair."""
    from webqa import __version__

    def ordenavel(v: str) -> tuple:
        numeros = tuple(int(x) for x in re.findall(r"\d+", v.split(".dev")[0])[:3])
        return numeros + (0,) * (3 - len(numeros))

    assert ordenavel(__version__) >= ordenavel(ultima_release()["versao"])


# ---------- A cadeia morde? ----------
#
# As asserções acima são sobre dados; estas são sobre objetos git de verdade, num
# repositório fabricado. É a diferença entre "o manifesto está bem formado" e "a
# tag ancora o que diz ancorar" — e só a segunda é a promessa que o consumidor
# guarda. Uma guarda de release que nunca foi vista recusando é decoração cara.


@pytest.fixture
def repo_fabricado(tmp_path, monkeypatch):
    """Um repositório mínimo com o layout desta casa: pacote em `webqa-suite/`."""
    import subprocess

    from scripts import publicar_release as pr

    raiz = tmp_path / "repo"
    (raiz / "webqa-suite" / "webqa").mkdir(parents=True)
    (raiz / "webqa-suite" / "webqa" / "__init__.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8")

    def git(*args):
        return subprocess.run(["git", *args], cwd=raiz, capture_output=True,  # noqa: S603,S607
                              text=True, check=True).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t"), git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-q", "-m", "conteudo validado")

    monkeypatch.setattr(pr, "RAIZ_REPO", raiz)
    monkeypatch.setattr(pr, "RAIZ", raiz / "webqa-suite")
    monkeypatch.setattr(pr, "DIR_RELEASES", raiz / "webqa-suite" / "releases")
    return raiz, git


def _manifesto_para(pr, raiz, git, **mudancas):
    """Emite o manifesto do HEAD, com o digest real, e devolve o texto serializado."""
    sha = git("rev-parse", "HEAD")
    m = manifesto_valido(commit_sha=sha, tree_digest=pr.tree_digest(sha), **mudancas)
    return m, pr.serializar(m)


def test_tag_sem_manifesto_e_ausencia_de_release(repo_fabricado):
    """O caso mais barato de acontecer: alguém tagueia à mão e pula o publicador."""
    from scripts import publicar_release as pr

    _, git = repo_fabricado
    git("tag", "-a", "v1.0.0", "-m", "na mao")
    problemas = pr.verificar("v1.0.0")
    assert any("ausência de release" in p for p in problemas), problemas


def test_release_que_mexe_em_outra_coisa_alem_do_manifesto_reprova(repo_fabricado):
    """O elo que "declarar o pai" poderia custar, se ninguém o cobrasse.

    Sem esta cobrança, conteúdo NÃO validado entraria na versão sob a bandeira de
    uma validação que rodou no pai — e o manifesto continuaria dizendo a verdade
    sobre um commit que não é o que a tag entrega.
    """
    from scripts import publicar_release as pr

    raiz, git = repo_fabricado
    _, texto = _manifesto_para(pr, raiz, git)
    (raiz / "webqa-suite" / "releases").mkdir(parents=True)
    (raiz / "webqa-suite" / "releases" / "v1.0.0.manifesto.json").write_text(texto, "utf-8")
    (raiz / "webqa-suite" / "clandestino.py").write_text("# nao validado\n", "utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "release v1.0.0 + carona")
    git("tag", "-a", "v1.0.0", "-m", "v1.0.0")

    problemas = pr.verificar("v1.0.0")
    assert any("além do manifesto" in p for p in problemas), problemas


def test_tag_numa_arvore_com_outra_versao_reprova(repo_fabricado):
    """A trava que impede a versão de mentir: o wheel sairia com outro número."""
    from scripts import publicar_release as pr

    raiz, git = repo_fabricado
    (raiz / "webqa-suite" / "webqa" / "__init__.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "bump que ninguem contou para a tag")
    _, texto = _manifesto_para(pr, raiz, git)
    (raiz / "webqa-suite" / "releases").mkdir(parents=True)
    (raiz / "webqa-suite" / "releases" / "v1.0.0.manifesto.json").write_text(texto, "utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "release v1.0.0")
    git("tag", "-a", "v1.0.0", "-m", "v1.0.0")

    problemas = pr.verificar("v1.0.0")
    assert any("__version__" in p for p in problemas), problemas


def test_o_tree_digest_nao_depende_da_config_local_de_fim_de_linha(repo_fabricado):
    """O falso vermelho que ESTA release levou, virado teste.

    `git archive` aplica a mesma conversão do checkout. Com `core.autocrlf=true` —
    o padrão da instalação do Git para Windows — ele emite CRLF, e o digest da
    MESMA árvore muda. Foi assim que a v1.0.0, correta e já publicada, foi recusada
    por `--verificar` num clone Windows.

    Uma guarda que reprova a release certa por causa do sistema de quem a confere é
    pior que guarda nenhuma: ela ensina a ignorar o vermelho, e o próximo vermelho
    será o verdadeiro. Aqui o digest é medido com a config LIGADA e com ela
    desligada, e os dois têm de ser o mesmo número.
    """
    from scripts import publicar_release as pr

    raiz, git = repo_fabricado
    (raiz / "webqa-suite" / "com_linhas.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "arquivo com fins de linha")
    sha = git("rev-parse", "HEAD")

    git("config", "core.autocrlf", "false")
    sem_conversao = pr.tree_digest(sha)
    git("config", "core.autocrlf", "true")
    com_conversao = pr.tree_digest(sha)

    assert sem_conversao == com_conversao, (
        "o digest da árvore mudou com `core.autocrlf` — a âncora passou a depender da "
        "configuração de quem confere, e a release certa reprova em metade das máquinas.")


def test_cadeia_integra_nao_reprova(repo_fabricado):
    """O outro lado, e ele é obrigatório: guarda que só sabe reprovar reprova tudo."""
    from scripts import publicar_release as pr

    raiz, git = repo_fabricado
    _, texto = _manifesto_para(pr, raiz, git)
    (raiz / "webqa-suite" / "releases").mkdir(parents=True)
    (raiz / "webqa-suite" / "releases" / "v1.0.0.manifesto.json").write_text(texto, "utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "release v1.0.0")
    git("tag", "-a", "v1.0.0", "-m", "v1.0.0")

    assert pr.verificar("v1.0.0") == []


def test_o_readme_instala_a_versao_publicada():
    """O caminho de instalação da E1 aponta para uma release que EXISTE.

    Até a E2 esta asserção era contra `__version__`; agora que a ponta anda à
    frente da release, comparar com ela mandaria instalar uma tag que ninguém
    cortou. A régua é a versão publicada, não a que está sendo escrita.
    """
    from scripts.caminho_de_instalacao import declarado

    assert declarado().ref == f"v{ultima_release()['versao']}"
