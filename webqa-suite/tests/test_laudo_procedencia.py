"""VERIFICAÇÃO: o laudo carimba a régua que o produziu (D6k).

O hash da lista curada no laudo fecha o buraco de §8.1/H2 da arquitetura de
padrão-em-harness: dois laudos que dizem "0 achados" com hashes diferentes
foram medidos por listas diferentes — a edição silenciosa deixa de ser
invisível. Sem rede: só serialização e hash de arquivo em tmp_path.
"""
from __future__ import annotations

import json

import pytest

from webqa.sondagem import (
    CaminhoSensivel,
    _bloco_padrao,
    _gravar_laudo,
    hash_dos_caminhos,
)

pytestmark = pytest.mark.verification

_LISTA = """\
- path: /.git/HEAD
  categoria: vcs
  severidade: alta
  content_type_esperado: text/plain
  remediacao: Remova o .git do docroot.
  procedencia: OWASP WSTG-CONF-004
"""


def _escrever(tmp_path, texto):
    caminho = tmp_path / "caminhos.yaml"
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def test_hash_tem_prefixo_e_e_estavel_para_o_mesmo_conteudo(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(_LISTA, encoding="utf-8")
    b.write_text(_LISTA, encoding="utf-8")
    assert hash_dos_caminhos(a).startswith("sha256:")
    assert hash_dos_caminhos(a) == hash_dos_caminhos(b), "mesmo conteúdo, mesmo hash"


def test_hash_muda_quando_a_lista_e_editada(tmp_path):
    """O ponto todo: remover uma linha da lista tem de mudar o hash. Sem isso,
    encurtar a lista em silêncio produz o mesmo carimbo e o mesmo '0 achados'."""
    cheia = _escrever(tmp_path, _LISTA)
    hash_cheia = hash_dos_caminhos(cheia)
    encurtada = _escrever(tmp_path, _LISTA.replace(
        "  procedencia: OWASP WSTG-CONF-004\n", ""))
    assert hash_dos_caminhos(encurtada) != hash_cheia


def test_bloco_padrao_carrega_hash_e_total(tmp_path):
    caminho = _escrever(tmp_path, _LISTA)
    caminhos = [CaminhoSensivel("/.git/HEAD", "vcs", "alta", "text/plain", "corrija"),
                CaminhoSensivel("/.env", "configuracao", "alta", "", "corrija")]
    bloco = _bloco_padrao(caminho, caminhos)
    assert bloco == {"caminhos_sensiveis_hash": hash_dos_caminhos(caminho),
                     "caminhos_total": 2}


def test_laudo_carrega_a_regua_antes_dos_alvos(tmp_path):
    saida = tmp_path / "laudo.json"
    padrao = {"caminhos_sensiveis_hash": "sha256:deadbeef", "caminhos_total": 5}
    _gravar_laudo(saida, [], padrao)
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["padrao"] == padrao
    # A régua vem antes dos alvos: quem lê topa com a procedência primeiro.
    assert list(dados)[0] == "padrao"


def test_laudo_sem_padrao_continua_valido(tmp_path):
    """Compatibilidade: sem o bloco, o laudo não ganha a chave nem quebra."""
    saida = tmp_path / "laudo.json"
    _gravar_laudo(saida, [])
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert "padrao" not in dados and "alvos" in dados
