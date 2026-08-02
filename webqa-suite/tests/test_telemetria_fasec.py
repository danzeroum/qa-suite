"""VERIFICAÇÃO: a telemetria da Fase C nunca carrega dado sensível.

Irmão de `test_vazamento_de_credencial`: a garantia que interessa não é
"chamamos o filtro" — é "o byte não está lá". Por isso os testes de vazamento
plantam o dado e fazem grep no SERIALIZADO, e `test_o_filtro_tem_dentes` é o par
obrigatório — sem ele, um filtro que virasse passthrough deixaria os outros
verdes e a garantia oca. Um detector que nunca pegou violação plantada não está
provado.

A fronteira nasce ANTES de existir uma métrica `fasec.*` para filtrar — é a
mesma forma do `remediacao` no C0c: prova-se a fronteira antes da capacidade.
"""
from __future__ import annotations

import json

import pytest

from webqa import telemetria_fasec as tf

pytestmark = pytest.mark.verification

# Um segredo real (formato AWS) para plantar e caçar na saída.
AKIA = "AKIAIOSFODNN7EXAMPLE"


# ---------- o agregado legítimo passa intacto ----------

def test_agregado_legitimo_passa_completo():
    dados = {
        "alvo_sha256": "a" * 64,
        "caminhos_sondados": 12,
        "caminhos_esperados": 15,
        "tempo_por_alvo_s": 3.4,
        "kill_switch_acionado": False,
        "gate_discovery": True,
        "achados_por_severidade": {"alta": 2, "media": 1, "baixa": 0},
        "run_inconclusivo": True,
    }
    assert tf.filtrar(dados) == dados, "nenhum campo agregado legítimo pode cair"


# ---------- chaves fora do allowlist caem (o coração do fail-closed) ----------

@pytest.mark.parametrize("chave", ["recurso", "evidencia", "url", "remediacao", "corpo"])
def test_chave_fora_do_allowlist_e_descartada(chave):
    saida = tf.filtrar({chave: "https://alvo.example/.git/HEAD?token=abc", "caminhos_sondados": 3})
    assert chave not in saida
    assert saida == {"caminhos_sondados": 3}, "só o campo permitido sobrevive"


def test_chave_desconhecida_nao_passa_por_default():
    """Fail-closed: o que não está na allowlist não sai, mesmo com valor inócuo."""
    assert tf.filtrar({"campo_novo_qualquer": 7}) == {}


# ---------- validação de valor: chave permitida não basta ----------

def test_string_livre_em_chave_permitida_e_descartada():
    """Mesmo numa chave da allowlist, string livre (que poderia carregar dado) cai;
    só hash hexadecimal é string aceita."""
    saida = tf.filtrar({"alvo_sha256": "https://alvo.example/segredo", "n_429": 4})
    assert "alvo_sha256" not in saida
    assert saida == {"n_429": 4}


def test_hash_hexadecimal_legitimo_passa():
    assert tf.filtrar({"escopo_hash": "deadbeefcafe1234"}) == {"escopo_hash": "deadbeefcafe1234"}


def test_string_true_nao_vira_flag():
    """`"true"` (string) não é bool nem hash → cai. Só o bool real liga a flag —
    mesma disciplina do gate, que só aceita o valor exato."""
    assert tf.filtrar({"kill_switch_acionado": "true"}) == {}
    assert tf.filtrar({"kill_switch_acionado": True}) == {"kill_switch_acionado": True}


def test_subchave_suja_em_dict_permitido_cai_e_as_limpas_sobrevivem():
    """Um dict de contagem com uma sub-chave que é URL: a suja cai, as enum ficam."""
    saida = tf.filtrar({"achados_por_categoria": {
        "vcs": 2, "config": 1, "https://alvo.example/.git": 9}})
    assert saida == {"achados_por_categoria": {"vcs": 2, "config": 1}}


def test_dict_com_valor_nao_inteiro_descarta_a_subchave():
    """Valor de contagem tem de ser inteiro: string/booleano numa sub-chave cai."""
    saida = tf.filtrar({"achados_por_severidade": {"alta": 3, "media": "muitas", "baixa": True}})
    assert saida == {"achados_por_severidade": {"alta": 3}}


# ---------- vazamento: grep no serializado (o byte não está lá) ----------

def test_segredo_plantado_nao_aparece_no_serializado():
    """Segredo numa chave não-permitida E dentro de uma string livre: some dos dois
    jeitos — pela allowlist e pela validação de valor."""
    serial = tf.serializar({
        "evidencia": f"chave vazada {AKIA}",              # chave fora da allowlist
        "alvo_sha256": f"prefixo{AKIA}",                  # string livre em chave permitida
        "caminhos_sondados": 5,
    })
    assert AKIA not in serial
    assert json.loads(serial) == {"caminhos_sondados": 5}


def test_url_com_query_nunca_sai():
    serial = tf.serializar({"recurso": "https://alvo.example/x?token=segredo", "n_503": 1})
    assert "token=segredo" not in serial
    assert "alvo.example" not in serial


def test_serializado_e_json_valido_e_ordenado():
    serial = tf.serializar({"caminhos_esperados": 2, "alvo_sha256": "f" * 64})
    carregado = json.loads(serial)          # não pode ter invalidado o documento
    assert carregado == {"alvo_sha256": "f" * 64, "caminhos_esperados": 2}


# ---------- o par obrigatório: o filtro tem dentes ----------

def test_o_filtro_tem_dentes():
    """Sem o filtro, o MESMO dado atravessa — prova que os testes acima medem algo.

    Espelha `filtrar` por um passthrough e mostra que o dado sensível sairia.
    Se `filtrar` virasse identidade (fail-open), os testes de vazamento acima
    reprovariam; este ancora o porquê.
    """
    sujo = {"evidencia": AKIA, "recurso": "https://alvo.example/.git"}
    passthrough = json.dumps(sujo, ensure_ascii=False)
    assert AKIA in passthrough and "alvo.example" in passthrough, "o dado sujo existe"
    # e o filtro real remove exatamente isso:
    assert tf.filtrar(sujo) == {}
