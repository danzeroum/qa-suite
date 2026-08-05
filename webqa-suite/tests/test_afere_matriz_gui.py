"""VERIFICAÇÃO: a guarda da matriz noturna reprova o que ela existe para pegar.

A guarda vive num script próprio (e não num trecho embutido no YAML) pelo mesmo
motivo da OS-44: assim ela ganha teste. Guarda sem teste é a classe de defeito
"a garantia existe, a ligação não" — e uma guarda de conta que não confere nada
é pior que nenhuma, porque parece cobertura.
"""
from __future__ import annotations

import pytest

from scripts.afere_matriz_gui import aferir, resumo

pytestmark = pytest.mark.verification


def _laudo(resultados, contagem=None):
    contagem = contagem or {}
    return {"results": resultados, "by_dimension": {"gui": contagem}}


def _r(nome, outcome="passed", detail="", dimension="gui"):
    return {"test": nome, "outcome": outcome, "detail": detail,
            "dimension": dimension, "dimensions": [dimension]}


def test_matriz_completa_e_coerente_passa():
    laudo = _laudo([_r("a"), _r("b", "failed"), _r("c", "skipped", "webkit ausente")],
                   {"passed": 1, "failed": 1, "skipped": 1})
    assert aferir(laudo) == ""


def test_dimensao_ausente_reprova():
    """O caso mais barato de acontecer e o mais fácil de não ver: a seleção
    errada roda zero check de GUI e o pytest sai 0."""
    assert "não rodou" in aferir(_laudo([_r("x", dimension="lgpd")]))


def test_conta_que_nao_fecha_reprova():
    """Um check que some entre a execução e o consolidado não deixa marca em
    contagem nenhuma — é exatamente o buraco que esta guarda existe para tapar."""
    laudo = _laudo([_r("a"), _r("b"), _r("c")], {"passed": 2})
    motivo = aferir(laudo)
    assert "a conta não fecha" in motivo and "3 resultados" in motivo


def test_skip_sem_motivo_reprova():
    """Skip anônimo é como uma engine some da conta sem ninguém notar: o laudo
    fica indistinguível entre "as três concordaram" e "só uma rodou"."""
    laudo = _laudo([_r("a"), _r("b", "skipped", "")], {"passed": 1, "skipped": 1})
    assert "SEM motivo escrito" in aferir(laudo)


def test_skip_com_motivo_e_aceito():
    """Pular é legítimo — engine não instalada, viewport fora da seleção. O que
    não é legítimo é pular calado."""
    laudo = _laudo([_r("a", "skipped", "firefox indisponível: rode playwright install")],
                   {"skipped": 1})
    assert aferir(laudo) == ""


def test_erro_entra_na_conta():
    """`error` não é `failed`, e somar só os dois primeiros faria um erro de
    setup desaparecer da conferência."""
    laudo = _laudo([_r("a", "error", "fixture estourou")], {"error": 1})
    assert aferir(laudo) == ""


def test_o_resumo_mostra_os_pulados_com_motivo():
    """O artefato precisa dizer O QUE não rodou; o número sozinho não permite
    conferir se o que faltou era o que importava."""
    laudo = _laudo([_r("a", "skipped", "webkit indisponível")], {"skipped": 1})
    texto = resumo(laudo)
    assert "webkit indisponível" in texto and "a" in texto
