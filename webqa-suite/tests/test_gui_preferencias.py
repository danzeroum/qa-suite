"""VERIFICAÇÃO: o filtro de animações, que é o miolo do check de movimento.

Um check que contasse toda animação viva acusaria de violação toda página que
anima na entrada e para — ou seja, toda página bem-feita. O valor do check não
está em ler `getAnimations()`; está em decidir o que conta.

Os casos vêm em pares deliberados: para cada coisa que CONTA há a vizinha que
não conta, porque é a fronteira entre as duas que um filtro ingênuo erra.
"""
import pytest

from webqa.movimento import (
    RESTANTE_MINIMO_MS,
    Animacao,
    animacoes_persistentes,
    resumo_de_animacoes,
)

pytestmark = pytest.mark.verification


def _bruta(nome="girar", alvo="span.gira", estado="running", restante_ms=None):
    return {"nome": nome, "alvo": alvo, "estado": estado, "restante_ms": restante_ms}


# ---------- Conta ----------

def test_animacao_infinita_conta():
    """Ausência de fim é o caso mais grave: nada faz parar."""
    persistentes = animacoes_persistentes([_bruta(restante_ms=None)])
    assert [a.nome for a in persistentes] == ["girar"]
    assert persistentes[0].infinita


def test_animacao_com_mais_de_um_segundo_pela_frente_conta():
    assert len(animacoes_persistentes([_bruta(restante_ms=RESTANTE_MINIMO_MS + 1)])) == 1


# ---------- Não conta ----------

def test_animacao_de_entrada_que_ja_terminou_nao_conta():
    """O falso positivo óbvio: a página anima ao carregar e para.

    Uma de 800ms já acabou quando a janela de observação fecha (networkidle mais
    um segundo). Contá-la reprovaria justamente quem faz a coisa certa.
    """
    assert animacoes_persistentes([_bruta(nome="entrada", restante_ms=0)]) == []


def test_rabicho_abaixo_do_limiar_nao_conta():
    """O que resta termina antes de a pessoa perceber. Reprovar por isso seria
    cobrar perfeição em vez de conforto."""
    assert animacoes_persistentes([_bruta(restante_ms=RESTANTE_MINIMO_MS - 1)]) == []


def test_no_limiar_exato_nao_conta():
    """`>` estrito: exatamente um segundo restante fica de fora."""
    assert animacoes_persistentes([_bruta(restante_ms=RESTANTE_MINIMO_MS)]) == []


def test_animacao_pausada_nao_conta():
    """`getAnimations()` devolve pausadas e terminadas junto com as ativas.

    Uma animação pausada não incomoda ninguém — e um filtro que olhasse só a
    duração a contaria como infinita, porque pausada é justamente a que não tem
    tempo restante avançando.
    """
    assert animacoes_persistentes([_bruta(estado="paused", restante_ms=None)]) == []


def test_animacao_terminada_nao_conta():
    assert animacoes_persistentes([_bruta(estado="finished", restante_ms=0)]) == []


# ---------- Conjunto e mensagem ----------

def test_separa_o_que_conta_do_que_nao_conta_na_mesma_pagina():
    """Uma página real tem as duas coisas ao mesmo tempo."""
    brutas = [
        _bruta(nome="entrada", restante_ms=0),               # já acabou
        _bruta(nome="girar", restante_ms=None),              # infinita
        _bruta(nome="pulsar", estado="paused", restante_ms=None),
        _bruta(nome="deslizar", restante_ms=5000),           # ainda vai durar
    ]
    assert sorted(a.nome for a in animacoes_persistentes(brutas)) == ["deslizar", "girar"]


def test_pagina_sem_animacao_nao_inventa_violacao():
    assert animacoes_persistentes([]) == []


def test_mensagem_nomeia_alvo_e_quanto_falta():
    """Sem o alvo, quem lê o achado não sabe qual elemento se mexe; sem o tempo,
    não sabe se é um rabicho ou um carrossel eterno."""
    texto = resumo_de_animacoes([
        Animacao(nome="girar", alvo="span.gira", restante_ms=None),
        Animacao(nome="deslizar", alvo="div.banner", restante_ms=4200),
    ])
    assert "girar em span.gira (infinita)" in texto
    assert "deslizar em div.banner (4200ms restantes)" in texto


def test_resumo_trunca_dizendo_quantos_ficaram():
    animacoes = [Animacao(nome=f"a{i}", alvo="x") for i in range(15)]
    assert "e mais 5" in resumo_de_animacoes(animacoes, teto=10)


def test_bruta_sem_campos_nao_estoura():
    """Coletor que devolva menos do que o esperado vira animação com valores
    neutros, não exceção: instrumentação não pode derrubar a observação."""
    [animacao] = animacoes_persistentes([{}])
    assert animacao.infinita and animacao.alvo == "?"


def test_aceita_objeto_ja_construido():
    """A função é usada tanto sobre o retorno do navegador quanto sobre objetos
    fabricados nos testes — as duas formas têm de valer."""
    assert len(animacoes_persistentes([Animacao(nome="x", alvo="y")])) == 1


@pytest.mark.parametrize("restante", [0, 100, RESTANTE_MINIMO_MS])
def test_borda_da_janela_em_varios_pontos(restante):
    assert animacoes_persistentes([_bruta(restante_ms=restante)]) == []
