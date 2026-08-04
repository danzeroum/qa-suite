"""VERIFICAÇÃO do empacotamento instalável (frente E, E1).

O entrypoint é o que permite DECLARAR a suíte como dependência em vez de COPIÁ-la
(docs/…/ARQUITETURA §9). Estes testes travam o contrato do pyproject sem instalar
nada: leem os metadados e conferem que o alvo do console script existe de fato.
"""
from __future__ import annotations

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


def test_alvo_do_entrypoint_existe_e_e_chamavel():
    """O que o console script promete tem de existir — senão instala quebrado."""
    from webqa.sondagem import main
    assert callable(main)


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
