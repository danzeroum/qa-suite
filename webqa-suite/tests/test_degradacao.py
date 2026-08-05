"""VERIFICAÇÃO: o avaliador de degradação, sobre DOM fabricado.

O defeito que este arquivo existe para impedir é o **falso positivo**, e ele tem
endereço: `undefined is not a function` aparece no fonte de meia internet, dentro
de `<script>`, de comentário ou de atributo. Um avaliador que procurasse termo
proibido no HTML cru reprovaria alvo conforme — e reprovar o correto é o defeito
mais caro que uma bateria pode ter, porque o time desliga o check na segunda
semana e perde junto os achados verdadeiros.

Por isso a distinção "texto visível × HTML" tem teste próprio, e por isso ela é o
primeiro bloco daqui.

A validação (execução real contra o alvo fabricado, nos quatro modos de falha)
fica nos checks e está registrada no PR.
"""
from __future__ import annotations

import pytest

from webqa.degradacao import (
    TETO_DE_ENDPOINTS,
    Vocabulario,
    avaliar,
    carregar_vocabulario,
    endpoints_de_mesma_origem,
    excedeu_tentativas,
    texto_visivel,
)

pytestmark = pytest.mark.verification

VOCABULARIO = Vocabulario(
    termos_proibidos=("Traceback", "SyntaxError", "undefined is not"),
    vocabulario_de_erro=("erro", "falha", "indisponivel", "tente novamente"),
)

SAUDAVEL = "<html><body><main><h1>Loja</h1><p id='p'>3 pedidos</p></main></body></html>"


def _pagina(corpo: str) -> str:
    return f"<html><body><main><h1>Loja</h1>{corpo}</main></body></html>"


def _avaliar(corpo: str, saudavel: str = SAUDAVEL):
    return avaliar(_pagina(corpo), saudavel, vocabulario=VOCABULARIO)


# ---------- Texto visível × HTML: o recorte que evita o falso positivo ----------

def test_termo_proibido_em_texto_visivel_reprova():
    laudo = _avaliar("<p>Erro: SyntaxError: Unexpected token '&lt;'</p>")
    assert laudo.termos_vazados == ("SyntaxError",)


def test_o_mesmo_termo_dentro_de_script_nao_conta():
    """`<script>` não está na tela de ninguém. Contá-lo reprovaria qualquer alvo
    que carregue uma biblioteca com a palavra no fonte."""
    laudo = _avaliar("<p>3 pedidos</p><script>if (x === undefined) "
                     "throw new SyntaxError('x');</script>")
    assert laudo.termos_vazados == ()


def test_o_mesmo_termo_em_comentario_nao_conta():
    laudo = _avaliar("<p>3 pedidos</p><!-- TODO: tratar SyntaxError do parse -->")
    assert laudo.termos_vazados == ()


def test_o_mesmo_termo_em_atributo_nao_conta():
    laudo = _avaliar('<p data-erro="SyntaxError" title="Traceback">3 pedidos</p>')
    assert laudo.termos_vazados == ()


def test_o_mesmo_termo_escondido_pelo_proprio_elemento_nao_conta():
    """`hidden`, `aria-hidden` e `display:none` inline: o elemento existe e não
    está na tela. É o caso do template de erro que a página nunca mostrou."""
    for corpo in ('<p hidden>SyntaxError</p>',
                  '<p aria-hidden="true">SyntaxError</p>',
                  '<p style="display: none">SyntaxError</p>',
                  '<template><p>SyntaxError</p></template>'):
        assert _avaliar(corpo + "<p>3 pedidos</p>").termos_vazados == (), corpo


def test_limite_declarado_folha_externa_nao_e_lida():
    """**Falso positivo conhecido e escolhido.**

    A avaliação é sobre o DOM serializado, sem CSSOM: elemento escondido por uma
    folha de estilo EXTERNA conta como visível. A direção do erro é deliberada —
    o termo técnico continua tendo sido entregue ao navegador, a um
    `display:block` de distância da tela — e está declarada para que ninguém a
    "corrija" achando que achou um bug.
    """
    laudo = _avaliar('<p class="oculto-por-css">SyntaxError</p>')
    assert laudo.termos_vazados == ("SyntaxError",)


def test_texto_visivel_ignora_o_head():
    """`<title>` é do navegador, não da página."""
    assert "Traceback" not in texto_visivel(
        "<html><head><title>Traceback</title></head><body><p>ok</p></body></html>")


# ---------- Tela branca ----------

def test_main_sem_texto_e_tela_branca():
    dom = "<html><body><main></main><footer>rodape</footer></body></html>"
    assert avaliar(dom, SAUDAVEL, vocabulario=VOCABULARIO).tela_branca


def test_main_com_texto_nao_e_tela_branca():
    assert not _avaliar("<p>3 pedidos</p>").tela_branca


def test_alvo_sem_main_cai_para_o_body_em_vez_de_acusar_tela_branca():
    """Ausência de marcação semântica não é ausência de conteúdo — são dois
    defeitos, e confundi-los acusaria de tela branca toda página sem `<main>`."""
    dom = "<html><body><p>Conteudo sem main</p></body></html>"
    assert not avaliar(dom, SAUDAVEL, vocabulario=VOCABULARIO).tela_branca


def test_body_realmente_vazio_e_tela_branca():
    assert avaliar("<html><body></body></html>", SAUDAVEL,
                   vocabulario=VOCABULARIO).tela_branca


# ---------- Mensagem: presente, ausente, e o que já estava lá ----------

def test_mensagem_de_erro_nova_e_reconhecida():
    laudo = _avaliar("<p>Nao foi possivel carregar. Tente novamente em instantes.</p>")
    assert laudo.mensagem_visivel


def test_silencio_nao_e_mensagem():
    """O caso que vira `xfail` no check: a página não disse nada."""
    laudo = _avaliar("<p id='p'>carregando pedidos...</p>")
    assert not laudo.mensagem_visivel
    assert not laudo.tela_branca
    assert laudo.termos_vazados == ()


def test_texto_que_JA_ESTAVA_na_tela_nao_conta_como_resposta_a_falha():
    """Sem a comparação com a carga saudável, um rodapé com "em caso de erro,
    ligue para…" faria todo alvo passar sem tratar falha nenhuma."""
    saudavel = ("<html><body><main><p>3 pedidos</p>"
                "<p>Em caso de erro, ligue para o suporte.</p></main></body></html>")
    laudo = avaliar(saudavel, saudavel, vocabulario=VOCABULARIO)
    assert not laudo.mensagem_visivel, "nada mudou na tela: não houve resposta à falha"


def test_acento_nao_esconde_a_palavra():
    """`indisponível` e `indisponivel` são a mesma palavra para quem lê a tela."""
    assert _avaliar("<p>Servico indisponível no momento.</p>").mensagem_visivel


def test_caixa_nao_esconde_o_termo_proibido():
    assert _avaliar("<p>ERRO: TRACEBACK (most recent call last)</p>").termos_vazados


def test_o_trecho_da_evidencia_e_sanitizado():
    """O achado se sustenta em TEXTO — e texto do alvo passa pela borda de escrita
    da casa antes de virar string, porque tela de erro real exibe dado de quem
    estava logado. É a spec de maior risco de PII do conjunto."""
    laudo = _avaliar("<p>Erro ao processar joao@exemplo.com</p>")
    assert "joao@exemplo.com" not in laudo.trecho
    assert "Erro ao processar" in laudo.trecho


# ---------- Tentativas: o comparador, fixado ----------

def test_no_teto_exato_a_pagina_ainda_esta_dentro():
    """Repetição com recuo exponencial é comportamento LEGÍTIMO. O teto separa
    "tentou de novo" de "está martelando o servidor caído" — e no teto exato a
    página ainda faz o que se pede dela. Mesma disciplina de borda do 50ms do
    TBT (OS-46) e dos 25% de cobertura de foco (OS-43)."""
    assert not excedeu_tentativas(5, 5)


def test_uma_acima_do_teto_reprova():
    assert excedeu_tentativas(6, 5)


def test_zero_tentativa_nao_reprova():
    assert not excedeu_tentativas(0, 5)


# ---------- Descoberta de endpoints: passiva, e só de mesma origem ----------

_ORIGEM = "http://127.0.0.1:8000"


def test_terceiro_nunca_entra_na_lista():
    """A regra não é eficiência: interceptar a chamada de um alvo a um serviço de
    terceiro não observaria a resiliência do alvo, e faria a suíte agir sobre uma
    relação que não é dela."""
    requisicoes = [("https://analytics.invalid/coleta", "fetch"),
                   (f"{_ORIGEM}/api/pedidos", "fetch")]
    assert endpoints_de_mesma_origem(requisicoes, _ORIGEM) == (f"{_ORIGEM}/api/pedidos",)


def test_so_xhr_e_fetch_entram():
    """Documento, imagem e folha de estilo não são chamadas de API — interceptá-las
    mediria outra coisa (e derrubaria o layout, acusando tela branca por engano)."""
    requisicoes = [(f"{_ORIGEM}/", "document"), (f"{_ORIGEM}/logo.png", "image"),
                   (f"{_ORIGEM}/estilo.css", "stylesheet"), (f"{_ORIGEM}/api/x", "xhr")]
    assert endpoints_de_mesma_origem(requisicoes, _ORIGEM) == (f"{_ORIGEM}/api/x",)


def test_ordena_pelo_mais_chamado():
    """O endpoint de maior volume é o que tem mais chance de alimentar a tela
    principal — e é o que o laudo precisa nomear."""
    requisicoes = [(f"{_ORIGEM}/api/raro", "fetch"),
                   (f"{_ORIGEM}/api/quente", "fetch"),
                   (f"{_ORIGEM}/api/quente", "fetch")]
    assert endpoints_de_mesma_origem(requisicoes, _ORIGEM)[0] == f"{_ORIGEM}/api/quente"


def test_respeita_o_teto_de_endpoints():
    """Interceptar tudo viraria uma simulação de "a internet caiu", que é outro
    cenário e tem outro nome."""
    requisicoes = [(f"{_ORIGEM}/api/{i}", "fetch") for i in range(10)]
    assert len(endpoints_de_mesma_origem(requisicoes, _ORIGEM)) == TETO_DE_ENDPOINTS


def test_alvo_sem_xhr_devolve_lista_vazia():
    """É o que faz o check PULAR com motivo, em vez de passar: ausência de
    endpoint não é resiliência comprovada."""
    assert endpoints_de_mesma_origem([(f"{_ORIGEM}/", "document")], _ORIGEM) == ()


def test_prefixo_parecido_nao_e_mesma_origem():
    """`http://127.0.0.1:8000.evil.com` começa com a origem como TEXTO e é outro
    host. Sem a barra separadora, a comparação por prefixo entregaria um terceiro
    para ser interceptado."""
    requisicoes = [("http://127.0.0.1:8000.evil.com/api", "fetch")]
    assert endpoints_de_mesma_origem(requisicoes, _ORIGEM) == ()


# ---------- Vocabulário: o YAML e o código não podem divergir ----------

def test_vocabulario_do_yaml_chega_carregado():
    """Chave que ninguém lê é a classe "a garantia existe, a ligação não": alguém
    acrescenta um termo ao YAML esperando que o check o cobre, e nada acontece."""
    vocabulario = carregar_vocabulario()
    assert "Traceback" in vocabulario.termos_proibidos
    assert "SyntaxError" in vocabulario.termos_proibidos, "medido contra o alvo na OS-47"
    assert "tente novamente" in vocabulario.vocabulario_de_erro


def test_vocabulario_ausente_nao_estoura(tmp_path):
    """YAML sem o bloco devolve vazio — e vazio faz o check não acusar nada, que é
    o lado seguro: instrumentação não pode ser a causa de uma execução perdida."""
    caminho = tmp_path / "perfis.yaml"
    caminho.write_text("viewports: {}\n", encoding="utf-8")
    vocabulario = carregar_vocabulario(caminho)
    assert vocabulario.termos_proibidos == ()
    assert _avaliar("<p>SyntaxError</p>") .termos_vazados, "com vocabulário, acusa"
    assert avaliar(_pagina("<p>SyntaxError</p>"), SAUDAVEL,
                   vocabulario=vocabulario).termos_vazados == ()
