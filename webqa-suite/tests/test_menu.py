"""VERIFICAÇÃO: a partição de desfechos do menu mobile, e o coletor conservador.

O critério de GUI-RESP-05 é o **"e"**: abre por clique **e** por teclado. Este
arquivo fixa duas coisas que a validação em navegador não fixaria sozinha:

1. **onde o veredito é duro e onde abranda.** Achar o gatilho é heurística — não
   existe marcação obrigatória para "isto abre o menu". Reprovar quando a
   heurística não achou nada seria reprovar por não saber, e é o erro que custa a
   credibilidade da bateria. Já "abre com mouse e não com teclado" não tem
   heurística nenhuma: o controle existe e não funciona;
2. **a fronteira do clique, NO COLETOR.** `a[href]` e `[type=submit]` são
   excluídos onde os candidatos nascem, não numa conferência posterior — filtro
   que depende de alguém lembrar de aplicá-lo é filtro que um dia não é aplicado.
"""
from __future__ import annotations

import pytest

from webqa.menu import (
    JS_GATILHOS,
    Gatilho,
    gatilho_de,
    motivo_de_abrandar,
    motivo_de_reprovar,
)

pytestmark = pytest.mark.verification


# ---------- O veredito duro: abre com mouse, não com teclado ----------

def test_div_onclick_que_abre_so_no_clique_reprova():
    """A assinatura do defeito: `<div onclick>` fazendo papel de botão. Não
    recebe foco, não responde a Enter, e funciona em todo teste feito com mouse
    — que é o que torna este defeito tão comum e tão invisível."""
    motivo = motivo_de_reprovar(Gatilho("div.menu-gatilho", focavel=False,
                                        abre_por_clique=True, abre_por_teclado=False))
    assert "NÃO recebe foco" in motivo
    assert "div.menu-gatilho" in motivo, "a mensagem nomeia o elemento a corrigir"
    assert "2.1.1" in motivo


def test_gatilho_focavel_que_ignora_Enter_e_Espaco_tambem_reprova():
    """Pior que o anterior em um aspecto: o controle PARECE acionável por
    teclado — recebe foco — e não é. Quem navega por teclado chega nele e nada
    acontece."""
    motivo = motivo_de_reprovar(Gatilho("span.menu", focavel=True,
                                        abre_por_clique=True, abre_por_teclado=False))
    assert "Enter e Espaço" in motivo


def test_gatilho_que_abre_dos_dois_jeitos_nao_reprova():
    assert motivo_de_reprovar(Gatilho("button.menu", focavel=True,
                                      abre_por_clique=True, abre_por_teclado=True)) == ""


def test_gatilho_que_nao_abre_de_jeito_nenhum_NAO_reprova():
    """Provavelmente não é o gatilho — e reprovar aqui seria reprovar a
    heurística, não o alvo. Cai no abrandamento."""
    assert motivo_de_reprovar(Gatilho("div.x", abre_por_clique=False)) == ""


# ---------- O abrandamento: onde a heurística acaba ----------

def test_sem_gatilho_encontrado_o_motivo_admite_as_duas_causas():
    """Pode ser navegação inalcançável (defeito) ou um gatilho que a heurística
    não reconhece. Dizer qual das duas sem saber é o que custa credibilidade."""
    motivo = motivo_de_abrandar(Gatilho(), "nav.principal")
    assert "nav.principal" in motivo
    assert "não reconhece" in motivo and "Sinal, não prova" in motivo


def test_candidato_que_navegou_e_declarado_como_link():
    """Menu que navega não é menu. A medição é abandonada em vez de seguir
    contra outra página — medir a página errada daria um veredito sobre um alvo
    que ninguém pediu."""
    motivo = motivo_de_abrandar(Gatilho("a.marca", navegou=True), "nav")
    assert "NAVEGOU" in motivo and "é link, não gatilho" in motivo


def test_traducao_do_bruto_com_ausencia():
    assert not gatilho_de(None).existe
    assert not gatilho_de({}).existe
    assert gatilho_de({"seletor": "button.x"}).existe


# ---------- A fronteira do clique, no coletor ----------

@pytest.mark.parametrize("proibido", ["a[href]", "submit"])
def test_o_coletor_exclui_link_e_submit_por_construcao(proibido):
    """A exclusão é no JS que gera os candidatos, e não numa conferência depois.

    São as duas coisas que um clique não pode tocar sem sair do território
    passivo de `webqa/gates.py`: link navega, submit escreve. Filtro que depende
    de alguém lembrar de aplicá-lo é filtro que um dia não é aplicado.
    """
    assert "proibido" in JS_GATILHOS
    assert "'A'" in JS_GATILHOS and "hasAttribute('href')" in JS_GATILHOS
    assert "'submit'" in JS_GATILHOS


def test_os_sinais_do_coletor_sao_estruturais_e_nao_de_nome():
    """Procurar a palavra "menu" no texto não sobreviveria a alvo em outro
    idioma, e um ícone de três traços não tem texto nenhum. O nome entra só como
    desempate."""
    for sinal in ("aria-expanded", "aria-controls", "onclick", "role=button"):
        assert sinal in JS_GATILHOS
