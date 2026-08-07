"""VERIFICAÇÃO da autoprova de mordida por release (frente E, E5).

Uma régua verde cujas travas não mordem é **indistinguível** de uma régua verde, e
a release é exatamente o momento em que alguém do outro lado passa a confiar nela
sem poder olhar. Estes testes travam três coisas:

1. **o escopo é o do contrato**, lido de `esperado.json` e nunca digitado aqui — a
   contagem sai da fonte, e um teste que restatasse "28" viraria a mentira do dia
   em que o contrato mudasse;
2. **`fora_do_contrato` entra COM MOTIVO**, como `declarado-sem-mordida`. Exigir
   mordida determinística de quem depende de rede, de engine instalada ou de tempo
   violaria a navalha do contrato — reprovaria por ambiente, nunca por regressão;
3. **a autoprova da autoprova**: uma mordida sabotada de propósito faz a release
   ser recusada. Sem isto, "todas mordem" seria uma frase, não uma medição.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.autoprova import (
    carregar_contrato,
    declarados_sem_mordida,
    direcoes_do_smoke,
    montar,
    morderam,
    selecao_do_contrato,
)
from scripts.publicar_release import Recusa, mordida_da_autoprova, problemas_de_forma

pytestmark = pytest.mark.verification

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def contrato() -> dict:
    return carregar_contrato()


def resultados_perfeitos(contrato: dict, sabotados: int = 0) -> list[dict]:
    """Resultados em que TODOS os `devem_falhar` reprovaram — menos os sabotados.

    Sabotar é fazer o check PASSAR contra a violação plantada: exatamente o que
    acontece quando uma regex quebra, um seletor muda ou alguém "conserta" o alvo
    fabricado sem atualizar o contrato.
    """
    esperados = list(contrato["devem_falhar"])
    return [{"test": n, "estado": "passed" if i < sabotados else "failed"}
            for i, n in enumerate(esperados)]


# ---------- O escopo vem do contrato ----------

def test_a_selecao_vem_do_proprio_contrato(contrato):
    """Contrato e execução divergindo é a forma mais silenciosa de a autoprova
    provar outra coisa que não o que promete provar."""
    assert selecao_do_contrato(contrato) == "lgpd or seguranca or gui"


def test_o_escopo_e_a_lista_do_contrato_inteira(contrato):
    """A contagem sai da FONTE. Um número escrito aqui viraria a mentira do dia em
    que alguém acrescentasse um check ao contrato."""
    mordidas, faltantes = morderam(contrato, resultados_perfeitos(contrato))
    assert not faltantes
    assert len(mordidas) == len(contrato["devem_falhar"])


def test_toda_entrada_fora_do_contrato_entra_com_motivo(contrato):
    """`declarado-sem-mordida` é uma decisão revisável; uma contagem seria a mesma
    lacuna que o contrato inteiro existe para não ter."""
    declarados = declarados_sem_mordida(contrato)
    assert len(declarados) == len(contrato["fora_do_contrato"])
    for entrada in declarados:
        assert entrada["motivo"].strip(), entrada["nodeid"]
        assert entrada["motivo"] == contrato["fora_do_contrato"][entrada["nodeid"]]


def test_nenhum_fora_do_contrato_e_cobrado_como_mordida(contrato):
    """A navalha, executável: o que depende de AMBIENTE não entra no escopo.

    Se entrasse, a release reprovaria em toda máquina sem firefox, sem rede ou fora
    da VPS — por ambiente, nunca por regressão, que é precisamente a propriedade
    que o contrato 1:1 existe para ter.
    """
    assert not (set(contrato["fora_do_contrato"]) & set(contrato["devem_falhar"]))


# ---------- A guarda do smoke morde nas duas direções ----------

def test_o_smoke_morde_nas_duas_direcoes():
    """Aprovar o laudo que exerceu de verdade não prova nada sozinho: uma guarda que
    devolvesse sempre "ok" faria exatamente isso."""
    direcoes = direcoes_do_smoke()
    assert direcoes["conforme_aprova"], "a guarda reprovou um smoke que exerceu de verdade"
    assert direcoes["verde_por_ausencia_reprova"], "tudo pulado passou pela guarda"
    assert direcoes["falso_positivo_reprova"], "falso positivo na página conforme passou"
    assert direcoes["dimensao_ausente_reprova"], "laudo sem a dimensão gui passou"


# ---------- A autoprova da autoprova ----------

def test_autoprova_completa_aprova(contrato):
    relatorio = montar(contrato, resultados_perfeitos(contrato), "")
    assert relatorio["aprovada"] is True
    assert relatorio["escopo"]["devem_falhar"]["nao_morderam"] == []


def test_uma_mordida_sabotada_reprova_a_autoprova(contrato):
    """UMA basta. "Quase todas mordem" não é uma categoria: a release ou está
    provada ou não está."""
    relatorio = montar(contrato, resultados_perfeitos(contrato, sabotados=1), "")
    assert relatorio["aprovada"] is False
    assert len(relatorio["escopo"]["devem_falhar"]["nao_morderam"]) == 1


def test_indeterminacao_nunca_aprova(contrato):
    """"Não consegui provar" e "provei que não morde" pedem reações diferentes — e
    a única coisa que as duas NÃO podem produzir é uma release aprovada."""
    relatorio = montar(contrato, resultados_perfeitos(contrato), "Chromium indisponível")
    assert relatorio["aprovada"] is False


def test_mordida_sabotada_faz_a_release_ser_recusada(contrato, tmp_path):
    """A AUTOPROVA DA AUTOPROVA, no ponto que importa: o publicador recusa.

    Não basta o relatório dizer `aprovada: false` — o que precisa acontecer é
    nenhuma ref nascer. É aqui que a medição vira consequência.
    """
    caminho = tmp_path / "autoprova.json"
    caminho.write_text(json.dumps(montar(contrato, resultados_perfeitos(contrato, sabotados=3), "")),
                       encoding="utf-8")
    with pytest.raises(Recusa, match="autoprova reprovou"):
        mordida_da_autoprova(caminho)


def test_indeterminacao_faz_a_release_ser_recusada(contrato, tmp_path):
    caminho = tmp_path / "autoprova.json"
    caminho.write_text(
        json.dumps(montar(contrato, resultados_perfeitos(contrato), "sem navegador")),
        encoding="utf-8")
    with pytest.raises(Recusa, match="não conseguiu provar"):
        mordida_da_autoprova(caminho)


def test_relatorio_ilegivel_faz_a_release_ser_recusada(tmp_path):
    """Relatório ausente ou quebrado é config inválida, jamais aprovação tácita."""
    with pytest.raises(Recusa, match="ilegível"):
        mordida_da_autoprova(tmp_path / "nao-existe.json")


# ---------- O que a autoprova carimba no manifesto ----------

def test_a_autoprova_aprovada_vira_numeros_no_manifesto(contrato, tmp_path):
    """`aprovada` exige os NÚMEROS, não a palavra: sem contagem, quem lê o manifesto
    vê "aprovada" e não tem como perguntar *aprovada em quê*."""
    caminho = tmp_path / "autoprova.json"
    relatorio = montar(contrato, resultados_perfeitos(contrato), "")
    caminho.write_text(json.dumps(relatorio), encoding="utf-8")

    mordida = mordida_da_autoprova(caminho)
    total = len(contrato["devem_falhar"])
    assert mordida["estado"] == "aprovada"
    assert mordida["devem_falhar"] == f"{total}/{total}"
    assert mordida["smoke_gui"] == "4/4"
    assert mordida["declarado_sem_mordida"] == len(contrato["fora_do_contrato"])


def test_manifesto_aprovado_sem_numeros_reprova():
    """A palavra sozinha é selo, e selo é o que o contrato chama de pior que fiscal
    nenhum."""
    manifesto = {
        "schema_version": "1.0", "repositorio": "danzeroum/qa-suite", "tag": "v1.0.0",
        "versao": "1.0.0", "commit_sha": "a" * 40, "tree_digest": "sha256:" + "b" * 64,
        "catalogo": {"caminhos_sensiveis_hash": "sha256:" + "c" * 64,
                     "checks_hash": "sha256:" + "d" * 64},
        "mordida": {"estado": "aprovada"},
    }
    problemas = problemas_de_forma(manifesto)
    assert any("Aprovada em quê" in p for p in problemas), problemas


def test_manifesto_aprovado_com_escopo_parcial_reprova():
    """"27/28 mordendo" é `pendente`, nunca `aprovada`. Parte do escopo provado é
    exatamente o estado que um selo esconderia."""
    manifesto = {
        "schema_version": "1.0", "repositorio": "danzeroum/qa-suite", "tag": "v1.0.0",
        "versao": "1.0.0", "commit_sha": "a" * 40, "tree_digest": "sha256:" + "b" * 64,
        "catalogo": {"caminhos_sensiveis_hash": "sha256:" + "c" * 64,
                     "checks_hash": "sha256:" + "d" * 64},
        "mordida": {"estado": "aprovada", "devem_falhar": "27/28", "smoke_gui": "4/4",
                    "declarado_sem_mordida": 15},
    }
    problemas = problemas_de_forma(manifesto)
    assert any("TODAS as mordidas" in p for p in problemas), problemas
