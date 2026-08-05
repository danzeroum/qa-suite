"""VERIFICAÇÃO: a guarda do smoke de GUI tem dentes.

Uma guarda que nunca reprovou não está provada. Esta existe para impedir o
`quality-gate` de ficar verde sem ter exercido a dimensão — e os casos que ela
precisa pegar são justamente os que não dá para produzir num CI de verdade sem
quebrar o CI de propósito.

É a lição do D6 aplicada à própria guarda do D6.
"""
import json

import pytest

from scripts.afere_smoke_gui import aferir, main

pytestmark = pytest.mark.verification


def _laudo(**gui):
    return {"by_dimension": {"gui": gui}} if gui else {"by_dimension": {}}


def test_smoke_que_exercitou_passa():
    assert aferir(_laudo(passed=7, failed=0, skipped=0)) == ""


def test_tudo_pulado_reprova():
    """O cenário do D6: sem Chromium os checks pulam, o pytest sai 0, e o job
    ficaria verde sem ter conferido nada. Verde por ausência não é verde."""
    motivo = aferir(_laudo(passed=0, failed=0, skipped=7))
    assert "nenhum check de GUI passou" in motivo
    assert "Chromium" in motivo, "a mensagem precisa dizer o que provavelmente falta"


def test_dimensao_ausente_reprova():
    """Marcador removido ou seleção errada: os checks nem foram coletados."""
    assert "não tem a dimensão" in aferir(_laudo())


def test_falso_positivo_na_pagina_conforme_reprova():
    """O que o smoke existe para pegar: um check de GUI reprovando página
    conforme. Passar aqui em silêncio deixaria o falso positivo chegar a um alvo
    real — e falso positivo em acessibilidade custa a bateria inteira."""
    motivo = aferir(_laudo(passed=6, failed=1, skipped=0))
    assert "REPROVARAM a página conforme" in motivo


def test_falha_vence_passagem_parcial():
    """Um check verde ao lado de um vermelho não compensa: a reprovação manda."""
    assert aferir(_laudo(passed=99, failed=1)) != ""


# ---------- Ponta a ponta (arquivo em disco) ----------

def test_main_aprova_laudo_bom(tmp_path, capsys):
    caminho = tmp_path / "summary.json"
    caminho.write_text(json.dumps(_laudo(passed=7)), encoding="utf-8")
    assert main([str(caminho)]) == 0
    assert "exercitado" in capsys.readouterr().out


def test_main_reprova_laudo_ruim(tmp_path):
    caminho = tmp_path / "summary.json"
    caminho.write_text(json.dumps(_laudo(passed=0, skipped=7)), encoding="utf-8")
    assert main([str(caminho)]) == 1


def test_laudo_ausente_reprova(tmp_path):
    """Smoke que não gerou laudo é smoke que não rodou — e isso é vermelho, não
    "nada a conferir"."""
    assert main([str(tmp_path / "nao-existe.json")]) == 1


def test_laudo_ilegivel_reprova(tmp_path):
    """JSON corrompido não pode virar aprovação silenciosa: instrumentação
    quebrada é ausência de medida, e ausência nunca vira PASS (§2.1)."""
    caminho = tmp_path / "summary.json"
    caminho.write_text("{isto nao e json", encoding="utf-8")
    assert main([str(caminho)]) == 1
