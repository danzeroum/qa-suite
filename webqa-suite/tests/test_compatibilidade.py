"""VERIFICAÇÃO: a comparação entre engines, sobre caixas fabricadas.

Dois defeitos, e os dois são silenciosos:

* **tolerância errada** — 1px a mais ou a menos muda a lista inteira de
  divergências, e o número resultante continua parecendo razoável;
* **comparar uma engine só** — sempre verde, e o verde é indistinguível do
  legítimo. É a regra 9 de `docs/GUI.md §2.2` na sua forma mais barata de
  cometer: basta o firefox não estar instalado.

Sem navegador: as caixas são fabricadas, e é isso que permite exercitar a borda
exata da tolerância — que numa engine de verdade depende da fonte instalada.
"""
from __future__ import annotations

import pytest

from webqa.compatibilidade import (
    CAMPOS_COMPARADOS,
    MINIMO_DE_ENGINES,
    ausentes_de,
    caixas_de,
    carregar_marcos,
    divergencias,
    erros_exclusivos,
    motivo_de_pular,
    pode_comparar,
)
from webqa.geometria import Caixa

pytestmark = pytest.mark.verification

TOLERANCIA = 4.0


def _caixa(seletor="h1", x=0.0, y=0.0, largura=100.0, altura=20.0) -> Caixa:
    return Caixa(seletor=seletor, x=x, y=y, largura=largura, altura=altura)


# ---------- Tolerância: a borda, fixada ----------

def test_engines_identicas_nao_divergem():
    por_engine = {"chromium": {"h1": _caixa()}, "firefox": {"h1": _caixa()}}
    assert divergencias(por_engine, tolerancia_px=TOLERANCIA) == ()


def test_na_tolerancia_exata_ainda_esta_dentro():
    """O comparador é `>`, não `>=`. Mesma disciplina de borda do 25% da
    cobertura de foco (OS-43), dos 50ms do TBT (OS-46) e dos 30% da
    sobreposição: a borda é decisão, e decisão tem teste."""
    por_engine = {"chromium": {"h1": _caixa(x=0)}, "firefox": {"h1": _caixa(x=TOLERANCIA)}}
    assert divergencias(por_engine, tolerancia_px=TOLERANCIA) == ()


def test_um_pixel_acima_da_tolerancia_diverge():
    por_engine = {"chromium": {"h1": _caixa(x=0)}, "firefox": {"h1": _caixa(x=TOLERANCIA + 1)}}
    achados = divergencias(por_engine, tolerancia_px=TOLERANCIA)
    assert len(achados) == 1
    assert achados[0].campo == "x" and achados[0].desvio == TOLERANCIA + 1


def test_compara_o_EXTREMO_e_nao_pares():
    """Com três engines, dois pares dentro da tolerância podem somar um desvio
    que estoura — e é o desvio total que a pessoa vê na tela. Comparar par a par
    aprovaria um layout com 8px de diferença entre a primeira e a terceira."""
    por_engine = {"chromium": {"h1": _caixa(x=0)},
                  "firefox": {"h1": _caixa(x=4)},
                  "webkit": {"h1": _caixa(x=8)}}
    achados = divergencias(por_engine, tolerancia_px=TOLERANCIA)
    assert len(achados) == 1 and achados[0].desvio == 8


def test_o_eixo_VERTICAL_fica_de_fora_e_o_motivo_foi_medido():
    """**Exclusão declarada, com número.**

    `y` e `altura` acumulam: cada diferença de métrica de fonte e de entrelinha
    da página inteira soma dentro deles. Medido na matriz local da OS-48, contra
    o alvo fabricado: `body` com 1776px no Chromium e 1797px no Firefox — 21px
    sem nada estar quebrado, só texto renderizado por duas engines. Um limiar que
    absorvesse isso já não pegaria defeito nenhum.

    O que se perde tem dono: colapso vertical que faz o elemento SUMIR é pego por
    `ausentes_de`; salto é pego pelo CLS por viewport; extravasamento, por
    GUI-RESP-01. Este teste existe para que a exclusão não seja desfeita por
    engano — desfazê-la reprova todo alvo com texto.
    """
    por_engine = {"chromium": {"body": _caixa(y=0, altura=1776)},
                  "firefox": {"body": _caixa(y=100, altura=1797)}}
    assert divergencias(por_engine, tolerancia_px=TOLERANCIA) == ()
    assert CAMPOS_COMPARADOS == ("x", "largura")


def test_a_mensagem_nomeia_cada_engine_e_o_valor_dela():
    """"Diverge 9px" sem dizer qual engine está fora manda quem corrige abrir as
    três — e é sempre uma que está diferente das outras duas."""
    por_engine = {"chromium": {"h1": _caixa(x=0)}, "webkit": {"h1": _caixa(x=9)}}
    texto = str(divergencias(por_engine, tolerancia_px=TOLERANCIA)[0])
    assert "chromium=0px" in texto and "webkit=9px" in texto and "h1" in texto


def test_divergencia_em_tamanho_tambem_conta():
    por_engine = {"chromium": {"h1": _caixa(largura=100)},
                  "firefox": {"h1": _caixa(largura=140)}}
    campos = {d.campo for d in divergencias(por_engine, tolerancia_px=TOLERANCIA)}
    assert campos == {"largura"}


# ---------- Marco ausente: o achado que não produz pixel nenhum ----------

def test_marco_que_some_numa_engine_nao_vira_divergencia_de_posicao():
    """É o achado mais grave e o mais fácil de perder: sem caixa não há desvio
    para medir, então a comparação diria "tudo dentro da tolerância" sobre uma
    página que perdeu a navegação inteira no WebKit."""
    por_engine = {"chromium": {"h1": _caixa(), "nav": _caixa("nav")},
                  "webkit": {"h1": _caixa()}}
    assert divergencias(por_engine, tolerancia_px=TOLERANCIA) == ()
    assert ausentes_de(por_engine) == {"nav": ("webkit",)}


def test_marco_presente_em_todas_nao_aparece_como_ausente():
    por_engine = {"chromium": {"h1": _caixa()}, "firefox": {"h1": _caixa()}}
    assert ausentes_de(por_engine) == {}


# ---------- O mínimo de duas engines ----------

def test_uma_engine_nao_permite_comparacao():
    """Skip, nunca "passou com uma": comparar uma engine consigo mesma é sempre
    verde, e esse verde é indistinguível do verde legítimo."""
    assert not pode_comparar(["chromium"])
    assert not pode_comparar([])
    assert pode_comparar(["chromium", "firefox"])
    assert MINIMO_DE_ENGINES == 2


def test_o_motivo_do_skip_diz_quantas_havia_e_como_instalar():
    """Skip sem o número é indistinguível de skip por preguiça — e quem lê o
    laudo não sabe se faltou uma engine ou se o check quebrou."""
    motivo = motivo_de_pular(["chromium"])
    assert "1 disponível" in motivo and "chromium" in motivo
    assert "playwright install" in motivo


# ---------- Erros exclusivos de engine ----------

def test_erro_que_aparece_em_todas_nao_e_exclusivo():
    """Já tem dono: `test_console_sem_erros_js`. Cobrá-lo de novo aqui faria o
    mesmo defeito aparecer duas vezes no laudo, e a correção de um apagaria o
    outro."""
    por_engine = {"chromium": ("404 /logo.png",), "firefox": ("404 /logo.png",)}
    assert erros_exclusivos(por_engine) == {}


def test_erro_de_uma_engine_so_e_exclusivo():
    por_engine = {"chromium": (), "firefox": ("SecurityError: X",), "webkit": ()}
    assert erros_exclusivos(por_engine) == {"firefox": ("SecurityError: X",)}


def test_sem_erro_nenhum_nao_produz_achado():
    assert erros_exclusivos({"chromium": (), "firefox": ()}) == {}


# ---------- Tradução e configuração ----------

def test_traduz_o_bruto_do_coletor():
    caixas = caixas_de({"h1": {"x": 1.5, "y": 2.5, "largura": 10.0, "altura": 20.0}})
    assert caixas["h1"].seletor == "h1" and caixas["h1"].altura == 20.0


def test_coletor_vazio_nao_estoura():
    assert caixas_de({}) == {} and caixas_de(None) == {}


def test_marcos_vem_do_yaml_e_nao_do_codigo():
    """Quem conhece o alvo decide o que é estrutural nele — e chave que ninguém
    lê é a classe "a garantia existe, a ligação não"."""
    marcos = carregar_marcos()
    assert marcos, "sem marcos declarados a comparação não teria o que medir"
    assert "h1" in marcos


def test_marcos_ausentes_do_yaml_nao_estouram(tmp_path):
    caminho = tmp_path / "perfis.yaml"
    caminho.write_text("viewports: {}\n", encoding="utf-8")
    assert carregar_marcos(caminho) == ()
