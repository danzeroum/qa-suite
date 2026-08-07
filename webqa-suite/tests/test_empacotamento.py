"""VERIFICAÇÃO do empacotamento instalável (frente E, E1).

O entrypoint é o que permite DECLARAR a suíte como dependência em vez de COPIÁ-la
(docs/…/ARQUITETURA §9). Estes testes travam o contrato do pyproject sem instalar
nada: leem os metadados e conferem que o alvo do console script existe de fato.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.verification

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def proj() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_build_system_torna_o_pacote_instalavel(proj):
    reqs = " ".join(proj["build-system"]["requires"])
    assert "setuptools" in reqs
    assert proj["build-system"]["build-backend"] == "setuptools.build_meta"


def test_entrypoint_do_motor_declarado(proj):
    scripts = proj["project"]["scripts"]
    assert scripts["webqa-sondar"] == "webqa.sondagem:main"


def test_entrypoint_do_veredito_declarado(proj):
    """E3: o veredito do processo é um console script IRMÃO, não um modo do pytest.

    Separado de propósito: um comando que também executasse os checks teria dois
    motivos para falhar, e quem lê o código de saída não saberia qual deles ocorreu.
    """
    scripts = proj["project"]["scripts"]
    assert scripts["webqa-veredicto"] == "webqa.veredito:main"


@pytest.mark.parametrize("modulo,funcao", [("webqa.sondagem", "main"),
                                           ("webqa.veredito", "main")])
def test_alvo_do_entrypoint_existe_e_e_chamavel(modulo, funcao):
    """O que o console script promete tem de existir — senão instala quebrado."""
    import importlib

    assert callable(getattr(importlib.import_module(modulo), funcao))


def test_dependencias_de_runtime_declaradas(proj):
    deps = " ".join(proj["project"]["dependencies"])
    for pacote in ("httpx", "beautifulsoup4", "lxml", "PyYAML"):
        assert pacote in deps, f"dependência de runtime ausente: {pacote}"
    # playwright é do navegador, não do motor: fica em extra, fora do core.
    assert "playwright" not in deps
    assert "playwright" in " ".join(proj["project"]["optional-dependencies"]["browser"])


def test_so_a_biblioteca_viaja_no_wheel(proj):
    """checks/tests/scripts/fixture_target não são o padrão instalável."""
    pacotes = proj["tool"]["setuptools"]["packages"]
    assert pacotes == ["webqa"]


def test_versao_e_fonte_unica_em_webqa(proj):
    """E4: a versão do pacote é dinâmica, vinda de webqa.__version__ — sem número
    duplicado no pyproject que pudesse divergir da régua carimbada no laudo."""
    assert "version" in proj["project"]["dynamic"]
    assert "version" not in proj["project"]           # não há valor estático duplicado
    assert proj["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "webqa.__version__"


def test_readme_declarado_e_existe(proj):
    """Um pacote publicável precisa de long_description: o README é a página do
    wheel/PyPI, e documenta a adoção (uses: auditar.yml / webqa-sondar)."""
    readme = proj["project"]["readme"]
    assert readme == "README.md"
    assert (_PYPROJECT.parent / readme).exists()


def test_versao_e_string_valida_para_tag_de_release():
    """E2: a versão precisa ser uma string PEP440 simples para uma tag `v<versao>`
    do release casar com ela."""
    import re

    from webqa import __version__
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?([abrc]\d+|\.dev\d+)?", __version__), __version__


# ---------- O caminho de instalação declarado (E1) ----------
#
# Empacotar não é distribuir. Os testes acima travam o que o wheel PROMETE; estes
# travam como alguém CHEGA a ele. Enquanto o caminho era `pip install webqa-suite`
# num comentário de README, a promessa do pacote estava conferida e a instalação
# não estava — e a instalação era a que falhava, porque o pacote não está em índice
# nenhum e o pyproject não vive na raiz do repositório.
#
# A forma é conferida AQUI (barato, offline); a EXECUÇÃO é do job
# `instalacao-declarada` do CI, que instala de verdade num ambiente limpo. Um
# caminho conferido só por regex continuaria podendo estar sintaticamente perfeito
# e materialmente quebrado.


@pytest.fixture(scope="module")
def caminho():
    from scripts.caminho_de_instalacao import declarado
    return declarado()


def test_readme_declara_um_caminho_de_instalacao_utilizavel(caminho):
    """A referência direta é a única forma que resolve hoje, e o README a declara."""
    assert caminho.nome == "webqa-suite"
    assert caminho.origem == "https://github.com/danzeroum/qa-suite"
    assert caminho.repo == "danzeroum/qa-suite"


def test_o_subdiretorio_do_caminho_e_onde_o_pyproject_realmente_esta(caminho):
    """A parte que ninguém adivinha: o pacote NÃO está na raiz do repositório.

    Conferido contra o disco, não contra uma string: mover o pacote de lugar sem
    atualizar o README passaria por esta guarda se ela comparasse texto com texto.
    """
    assert caminho.subdiretorio == _PYPROJECT.parent.name
    alvo = _PYPROJECT.parent.parent / caminho.subdiretorio / "pyproject.toml"
    assert alvo.exists(), (
        f"o README manda o pip procurar o projeto em {caminho.subdiretorio}/, e não há "
        f"pyproject.toml lá. Instalação declarada que não resolve é pior que instalação "
        f"não declarada: ela transfere a culpa para quem instala.")


def test_a_referencia_do_caminho_e_uma_tag_de_versao(caminho):
    """`@v<versao>` e não `@main`: a régua é a versão.

    Só a FORMA da referência é conferida aqui. QUAL versão ela nomeia é pergunta da
    release, e a resposta mudou na E2: até a tag existir, a única versão possível
    era a de `__version__`; publicada a v1.0.0 e bumpada a ponta, comparar com
    `__version__` mandaria instalar uma tag que ninguém cortou. A cobrança mora em
    tests/test_release.py::test_o_readme_instala_a_versao_publicada, contra o
    manifesto — a versão publicada, não a que está sendo escrita.
    """
    assert re.fullmatch(r"v\d+\.\d+\.\d+", caminho.ref), (
        f"o README instala de {caminho.ref!r}. `@main` e `@<sha>` funcionam, mas não são "
        f"régua: dois laudos tirados em dias diferentes mediriam padrões diferentes sem "
        f"que nada dissesse isso.")


def test_trocar_a_referencia_preserva_tudo_o_mais(caminho):
    """O que o CI executa é o caminho do README com o commit sob teste no lugar da tag.

    Se o job pudesse montar a string sozinho, ele passaria a provar a si mesmo: o
    README poderia perder o `#subdirectory=` sem que nada ficasse vermelho.
    """
    from scripts.caminho_de_instalacao import com_ref

    spec = com_ref(caminho, "abc1234")
    assert spec == (f"webqa-suite @ git+{caminho.origem}@abc1234"
                    f"#subdirectory={caminho.subdiretorio}")


def test_o_caminho_local_usa_a_autoridade_que_o_pip_aceita():
    """`file://localhost/…`, nunca `file:///…`.

    Medido, não suposto: com autoridade vazia o `packaging` recusa a URL da
    referência direta e o `pip` responde *"It looks like a path"* — que manda
    procurar defeito no argumento, e não na forma da URL. A reprodução offline do
    job (`make instalacao`) morreria nessa mensagem.
    """
    from scripts.caminho_de_instalacao import Caminho, local

    c = Caminho(spec="x", nome="webqa-suite", origem="https://github.com/danzeroum/qa-suite",
                repo="danzeroum/qa-suite", ref="v9.9.9", subdiretorio="webqa-suite")
    spec = local(c, "/tmp/clone", "abc1234")
    assert spec == "webqa-suite @ git+file://localhost/tmp/clone@abc1234#subdirectory=webqa-suite"


def test_a_leitura_do_caminho_recusa_readme_sem_declaracao(tmp_path):
    """A guarda pega o caso que a motivou: README que só diz `pip install webqa-suite`."""
    from scripts.caminho_de_instalacao import declarado

    readme = tmp_path / "README.md"
    readme.write_text("```bash\npip install webqa-suite\n```\n", encoding="utf-8")
    with pytest.raises(ValueError, match="não declara caminho de instalação"):
        declarado(readme)


def test_a_leitura_do_caminho_recusa_referencia_sem_subdiretorio(tmp_path):
    """E o caso que falha DEPOIS de parecer certo: referência direta sem o fragmento."""
    from scripts.caminho_de_instalacao import declarado

    readme = tmp_path / "README.md"
    readme.write_text(
        'pip install "webqa-suite @ git+https://github.com/danzeroum/qa-suite@v1.0.0"\n',
        encoding="utf-8")
    with pytest.raises(ValueError, match="subdirectory"):
        declarado(readme)
