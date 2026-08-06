"""VERIFICAÇÃO: as escalas da sessão moderada e a borda de PII (OS-54).

Vetores canônicos da literatura como teste: uma implementação de SUS que erra o
sinal dos itens pares produz números na mesma faixa (0–100) e plausíveis — o
defeito não tem sintoma, e só um gabarito conhecido o pega.
"""
import pytest
import yaml

from webqa.sessao import (
    FONTE_HUMANO,
    PESOS_SUM,
    SEVERIDADE_NIELSEN,
    Achado,
    Sessao,
    Tarefa,
    metricas_de,
    problemas_do_consentimento,
    seq,
    sum_de,
    sus,
)

pytestmark = pytest.mark.verification

CONSENTIMENTO = {"finalidade": "avaliar", "retencao_dias": 30, "expurgo": "apagar",
                 "gravacao": "tela", "data": "2026-08-06"}


# ---------- SUS contra os vetores canônicos ----------

def test_sus_gabarito_otimo_da_cem():
    """Ímpares no máximo, pares no mínimo — o padrão de resposta mais favorável."""
    assert sus([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0


def test_sus_gabarito_pessimo_da_zero():
    assert sus([1, 5, 1, 5, 1, 5, 1, 5, 1, 5]) == 0.0


def test_sus_todo_neutro_da_cinquenta():
    """O vetor que pega inversão de sinal: uma implementação que trate todos os
    itens como positivos também devolve 50 aqui, mas erra os dois acima."""
    assert sus([3] * 10) == 50.0


def test_sus_incompleto_nao_vira_numero():
    """Sete itens produziriam um valor na mesma faixa que não é comparável com
    nada. `None` diz 'não medi'; 70 diria 'medi e deu 70'."""
    assert sus([5] * 7) is None


def test_sus_fora_da_escala_nao_vira_numero():
    assert sus([6] * 10) is None and sus([0] * 10) is None


def test_sus_ausente_e_none():
    assert sus(None) is None


# ---------- SEQ ----------

def test_seq_valido():
    assert seq(5) == 5.0


def test_seq_ausente_nao_vira_zero():
    """A lei da casa aplicada a gente. E zero nem existe nesta escala, o que
    torna o erro mais visível: seria um valor fora do domínio lido como
    'muito difícil'."""
    assert seq(None) is None


@pytest.mark.parametrize("fora", [0, 8, -1, "5"])
def test_seq_fora_da_escala_e_none(fora):
    assert seq(fora) is None


# ---------- SUM ----------

def test_pesos_do_sum_somam_um_e_estao_declarados():
    """Qualquer combinação de três eixos num número só é uma ESCOLHA. Ela pode
    estar errada; o que não pode é estar escondida."""
    assert round(sum(PESOS_SUM.values()), 6) == 1.0
    assert set(PESOS_SUM) == {"conclusao", "satisfacao", "tempo"}


def test_sum_perfeito():
    t = Tarefa(cenario="c", concluiu=True, segundos=30, seq=7)
    assert sum_de([t], tempo_alvo_s=60) == 100.0


def test_sum_de_tarefa_abandonada_cai():
    """Derivado à mão, e a derivação corrigiu a expectativa e não o código:
    conclusão 0, satisfação (1−1)/(7−1) = 0, tempo min(1, 60/300) = 0,2.
    Média dos três = 0,0667 → 6,7. NÃO é zero, e não deve ser: 300s é lento, não
    infinitamente lento. Um SUM que zerasse aqui estaria dizendo que a pessoa
    não fez nada, quando ela tentou por cinco minutos."""
    t = Tarefa(cenario="c", concluiu=False, segundos=300, seq=1)
    assert sum_de([t], tempo_alvo_s=60) == 6.7


def test_sum_de_tarefa_abandonada_nao_chega_perto_de_aprovacao():
    """O que importa da borda acima: por pior que o eixo de tempo seja generoso,
    abandono não produz número que alguém leia como bom."""
    t = Tarefa(cenario="c", concluiu=False, segundos=1, seq=1)
    assert sum_de([t], tempo_alvo_s=60) < 40


def test_sum_nao_da_credito_por_ser_rapido_demais():
    """Concluir em metade do tempo não compensa uma tarefa que ninguém terminou."""
    rapido = Tarefa(cenario="c", concluiu=False, segundos=1, seq=1)
    assert sum_de([rapido], tempo_alvo_s=60) == round(100 / 3, 1)


def test_sum_sem_tarefa_avaliavel_e_none():
    assert sum_de([], tempo_alvo_s=60) is None
    assert sum_de([Tarefa(cenario="c")], tempo_alvo_s=60) is None


# ---------- métricas com origem ----------

def test_metricas_humanas_usam_os_nomes_das_sinteticas_com_fonte_marcada():
    s = Sessao(iniciais="MR", perfil="p",
               tarefas=(Tarefa(cenario="achar a política", concluiu=True,
                               segundos=47, cliques=3, seq=5),))
    m = metricas_de(s, tempo_alvo_s=60)
    assert "gui_jornada_tsr_achar_a_política" in m
    assert m["gui_jornada_tsr_achar_a_política"] == {"valor": 1, "fonte": FONTE_HUMANO}
    assert m["gui_jornada_tot_ms_achar_a_política"]["valor"] == 47000.0


def test_medida_ausente_nao_vira_chave():
    s = Sessao(iniciais="MR", perfil="p", tarefas=(Tarefa(cenario="c", concluiu=True),))
    m = metricas_de(s, tempo_alvo_s=60)
    assert "gui_jornada_tot_ms_c" not in m and "gui_sessao_seq_c" not in m


# ---------- achados ----------

def test_severidade_fora_de_nielsen_reprova_na_construcao():
    with pytest.raises(ValueError, match="severidade inválida"):
        Achado(descricao="x", severidade=5)


def test_rotulo_de_severidade_e_o_vocabulario_de_nielsen():
    assert Achado(descricao="x", severidade=4).rotulo == SEVERIDADE_NIELSEN[4]


# ---------- consentimento ----------

def test_consentimento_completo_passa():
    assert problemas_do_consentimento(CONSENTIMENTO) == []


@pytest.mark.parametrize("campo", ["finalidade", "retencao_dias", "expurgo",
                                   "gravacao", "data"])
def test_consentimento_sem_campo_obrigatorio_reprova(campo):
    incompleto = {k: v for k, v in CONSENTIMENTO.items() if k != campo}
    assert any(campo in p for p in problemas_do_consentimento(incompleto))


def test_retencao_indefinida_reprova():
    """Retenção sem prazo é o oposto de prazo declarado."""
    assert problemas_do_consentimento({**CONSENTIMENTO, "retencao_dias": 9999})


# ---------- a borda de PII ----------

def test_transcricao_com_pii_plantada_sai_sanitizada(tmp_path):
    """A pessoa vai dizer o próprio e-mail enquanto pensa em voz alta — é o que
    pensar em voz alta faz. Confiar em quem transcreve seria confiar na
    disciplina onde a casa exige mecanismo."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from scripts.consolida_sessao import carregar, consolidar

    ficha = tmp_path / "s.yaml"
    ficha.write_text(yaml.safe_dump({
        "iniciais": "MR", "perfil": "teclado", "consentimento": CONSENTIMENTO,
        "tarefas": [{"cenario": "c", "concluiu": True, "segundos": 10, "seq": 5}],
        "achados": [{"descricao": "disse o e-mail joao.silva@exemplo.com em voz alta",
                     "severidade": 2}],
        "notas": "contato dela: joao.silva@exemplo.com",
    }, allow_unicode=True), encoding="utf-8")
    saida = consolidar(carregar(ficha), 60)
    serializado = str(saida)
    assert "joao.silva@exemplo.com" not in serializado, (
        "PII atravessou a borda de escrita da sessão")


def test_ficha_com_nome_e_recusada_na_porta(tmp_path):
    """Minimização é de desenho, não de disciplina."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from scripts.consolida_sessao import carregar

    ficha = tmp_path / "s.yaml"
    ficha.write_text(yaml.safe_dump({"nome": "Maria", "iniciais": "MR"}), encoding="utf-8")
    with pytest.raises(ValueError, match="INICIAIS"):
        carregar(ficha)


# ---------- o dry-run como aceitação ----------

def test_o_modelo_de_ficha_do_repositorio_atravessa_o_consolidador():
    """O dry-run como teste: consolidador que nunca consumiu uma sessão é o
    `JS_PSEUDO_LOCALIZAR` do papel — instrumento completo que nada executa."""
    import sys
    from pathlib import Path as _P
    raiz = _P(__file__).resolve().parent.parent
    sys.path.insert(0, str(raiz))
    from scripts.consolida_sessao import carregar, consolidar

    saida = consolidar(carregar(raiz / "docs" / "exemplos" / "sessao-modelo.yaml"), 60)
    assert saida["metricas"], "a sessão-modelo não produziu métrica nenhuma"
    assert all(m["fonte"] == FONTE_HUMANO for m in saida["metricas"].values())
    assert len(saida["achados"]) >= 2
    assert saida["achados"][0]["severidade"] >= saida["achados"][-1]["severidade"]
    assert saida["consentimento"]["expurgar_ate"] == "2026-09-05"
