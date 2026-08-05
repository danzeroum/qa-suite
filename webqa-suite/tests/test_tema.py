"""VERIFICAÇÃO: a pré-checagem de tema escuro.

Sem ela, o check de contraste no escuro tem um modo de falha que não deixa
marca: num alvo SEM tema escuro o navegador renderiza o claro de novo, o axe não
acha nada de novo, e o teste passa anunciando cobertura de um tema que nunca foi
medido. O verde fica indistinguível do verde legítimo — regra 9 de
`docs/GUI.md §2.2` no seu pior formato.

Por isso a pré-checagem tem teste próprio, e por isso o limite dela está
declarado aqui, não só na docstring do módulo.
"""
import pytest

from webqa.tema import implementa_tema_escuro, motivo_de_pular

pytestmark = pytest.mark.verification


def test_fundos_diferentes_significam_tema_escuro():
    assert implementa_tema_escuro("rgb(255, 255, 255)", "rgb(34, 34, 34)")


def test_fundos_iguais_significam_ausencia_de_tema():
    """O caso que a pré-checagem existe para pegar."""
    assert not implementa_tema_escuro("rgb(255, 255, 255)", "rgb(255, 255, 255)")


def test_transparente_no_claro_e_pintado_no_escuro_conta_como_tema():
    """`rgba(0, 0, 0, 0)` é o que o navegador devolve quando ninguém pintou o
    body. Transparente no claro e `#222` no escuro É mudança de tema — e é
    exatamente o caso do alvo fabricado."""
    assert implementa_tema_escuro("rgba(0, 0, 0, 0)", "rgb(34, 34, 34)")


def test_diferenca_apenas_de_formatacao_nao_e_tema():
    """A mesma cor pode voltar como `rgb(34,34,34)` ou `rgb(34, 34, 34)`
    conforme a engine. Ler isso como mudança de tema inverteria justamente o
    veredito que esta função existe para dar — e o check passaria a medir o
    tema claro achando que mediu o escuro."""
    assert not implementa_tema_escuro("rgb(34,34,34)", "rgb(34, 34, 34)")


def test_maiusculas_nao_criam_tema():
    assert not implementa_tema_escuro("RGB(34, 34, 34)", "rgb(34, 34, 34)")


def test_limite_declarado_tema_que_muda_so_o_texto_cai_como_ausente():
    """**Falso negativo conhecido e deliberado.**

    Um alvo que escureça apenas a cor do TEXTO, mantendo o fundo, é lido aqui
    como "sem tema escuro" e o check pula. A escolha é do fundo porque ele é o
    sinal estável: a cor do texto varia por elemento, e comparar "algum elemento
    mudou" acusaria qualquer página com `:hover` ou foco.

    Pular com motivo é honesto. Medir o tema errado e passar não é — e é essa a
    troca que este teste registra, para que ninguém a desfaça por engano
    achando que está corrigindo um bug.
    """
    assert not implementa_tema_escuro("rgb(255, 255, 255)", "rgb(255, 255, 255)")


def test_valor_ausente_nao_estoura():
    """Coletor que devolva vazio não pode derrubar a observação: vira "sem
    tema", que é o lado seguro do erro (pula em vez de medir errado)."""
    assert not implementa_tema_escuro("", "")
    assert implementa_tema_escuro("", "rgb(34, 34, 34)")


def test_motivo_do_skip_diz_o_que_foi_medido():
    """Skip sem o valor medido é indistinguível de skip por preguiça — e quem lê
    o laudo não sabe se o alvo não tem tema ou se o check quebrou."""
    motivo = motivo_de_pular("rgb(255, 255, 255)")
    assert "rgb(255, 255, 255)" in motivo
    assert "não implementa tema escuro" in motivo
    assert "cor do TEXTO" in motivo, "o limite conhecido acompanha o skip"
